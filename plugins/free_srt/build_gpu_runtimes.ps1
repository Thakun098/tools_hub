param(
    [Parameter(Mandatory = $true)]
    [string]$WhisperCppSource,
    [string]$OutputRoot = "gpu-artifacts",
    [string]$Version = "1.9.1-freesrt.1",
    [ValidateSet("all", "cuda", "vulkan")]
    [string]$Backend = "all",
    [string]$CmakePath = "",
    [string]$VulkanSdk = ""
)

$ErrorActionPreference = "Stop"
$source = [IO.Path]::GetFullPath($WhisperCppSource)
$output = [IO.Path]::GetFullPath($OutputRoot)
if (-not (Test-Path -LiteralPath (Join-Path $source "CMakeLists.txt"))) {
    throw "Whisper.cpp source directory is missing CMakeLists.txt: $source"
}
New-Item -ItemType Directory -Force -Path $output | Out-Null

if (-not $CmakePath) {
    $cmakeCommand = Get-Command cmake -ErrorAction SilentlyContinue
    if ($cmakeCommand) {
        $CmakePath = $cmakeCommand.Source
    } else {
        $bundledCmake = Get-ChildItem "C:\Program Files (x86)\Microsoft Visual Studio" -Filter cmake.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $bundledCmake) { throw "CMake was not found" }
        $CmakePath = $bundledCmake.FullName
    }
}

# Some sandboxed Windows shells expose duplicate Path/PATH variables, which breaks MSBuild.
$processEnvironment = [Environment]::GetEnvironmentVariables("Process")
if ($processEnvironment.ContainsKey("Path") -and $processEnvironment.ContainsKey("PATH")) {
    $pathValue = $processEnvironment["Path"]
    [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
    [Environment]::SetEnvironmentVariable("Path", $pathValue, "Process")
}
if ($VulkanSdk) {
    $env:VULKAN_SDK = [IO.Path]::GetFullPath($VulkanSdk)
    $env:Path = "$env:VULKAN_SDK\Bin;$env:Path"
}

function Build-GpuRuntime([string]$RuntimeBackend, [string]$CmakeFlag) {
    $build = Join-Path $output "build-$RuntimeBackend"
    $stage = Join-Path $output "stage-$RuntimeBackend"
    $archive = Join-Path $output "FreeSRT-whisper-$RuntimeBackend-win-x64-$Version.zip"
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null

    & $CmakePath -S $source -B $build -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF $CmakeFlag
    if ($LASTEXITCODE -ne 0) { throw "CMake configure failed for $RuntimeBackend" }
    & $CmakePath --build $build --config Release --target whisper-cli --parallel 4
    if ($LASTEXITCODE -ne 0) { throw "CMake build failed for $RuntimeBackend" }

    $candidates = @(
        (Join-Path $build "bin\Release"),
        (Join-Path $build "bin"),
        (Join-Path $build "Release")
    )
    $binaryRoot = $candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ "whisper-cli.exe") } | Select-Object -First 1
    if (-not $binaryRoot) { throw "Could not find whisper-cli.exe for $RuntimeBackend" }

    Get-ChildItem -LiteralPath $binaryRoot -File | Where-Object {
        $_.Name -eq "whisper-cli.exe" -or $_.Extension.Equals(".dll", [StringComparison]::OrdinalIgnoreCase)
    } | Copy-Item -Destination $stage -Force

    $manifest = @{
        product = "FreeSRT whisper.cpp GPU runtime"
        backend = $RuntimeBackend
        version = $Version
        architecture = "win-x64"
        whisper_cpp_version = "1.9.1"
        built_at_utc = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText((Join-Path $stage "runtime-manifest.json"), $manifest, (New-Object Text.UTF8Encoding($false)))

    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $archive -CompressionLevel Optimal
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "$RuntimeBackend runtime: $archive" -ForegroundColor Green
    Write-Host "SHA-256: $hash"
}

if ($Backend -in @("all", "cuda")) { Build-GpuRuntime "cuda" "-DGGML_CUDA=ON" }
if ($Backend -in @("all", "vulkan")) { Build-GpuRuntime "vulkan" "-DGGML_VULKAN=ON" }
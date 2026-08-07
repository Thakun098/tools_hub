[CmdletBinding()]
param(
    [string]$VulkanRuntimeArchive = "",
    [ValidateSet("", "after-recovery-copy", "after-staged-build", "after-staged-validation", "after-archive-creation", "after-user-data-restore", "after-old-dist-move", "after-new-dist-promotion", "after-archive-promotion")]
    [string]$TestFaultPoint = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root "venv\Scripts\python.exe"
. (Join-Path $root "build_portable_helpers.ps1")

function Assert-PortableBinaryPolicy([string]$PortableRoot) {
    & $python -m freesrt.runtime_policy validate-portable --root $PortableRoot
    if ($LASTEXITCODE -ne 0) { throw "Portable package failed the shared runtime binary policy" }
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Missing venv Python: $python" }
if (-not (Test-Path -LiteralPath (Join-Path $root "bin\Release\whisper-cli.exe") -PathType Leaf)) { throw "Missing whisper.cpp binary" }
if (-not (Test-Path -LiteralPath (Join-Path $root "templates\index.html") -PathType Leaf)) { throw "Missing templates/index.html" }
if (-not (Test-Path -LiteralPath (Join-Path $root "static\app.js") -PathType Leaf)) { throw "Missing static/app.js" }
$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
$ffprobe = (Get-Command ffprobe -ErrorAction Stop).Source
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    $frontendModules = @(
        (Join-Path $root "static\app.js"),
        (Join-Path $root "static\js\dom.js"),
        (Join-Path $root "static\js\srt.js"),
        (Join-Path $root "static\js\state.js")
    )
    & $node.Source --experimental-vm-modules -e "const fs=require('fs'),vm=require('vm'); for(const path of process.argv.slice(1)){new vm.SourceTextModule(fs.readFileSync(path,'utf8'),{identifier:path}); console.log('Frontend module OK: '+path)}" @frontendModules
    if ($LASTEXITCODE -ne 0) { throw "Frontend JavaScript syntax validation failed" }
} else {
    Write-Warning "Node.js not found; skipped frontend JavaScript syntax validation"
}

$env:FFMPEG_SOURCE = $ffmpeg
$env:FFPROBE_SOURCE = $ffprobe
$buildId = [guid]::NewGuid().ToString("N")
$stageRoot = Join-Path $root "build\portable-staging\$buildId"
$stageDist = Join-Path $stageRoot "dist"
$stageWork = Join-Path $stageRoot "pyinstaller"
$recoveryRoot = Join-Path $root "build\portable-recovery\$buildId"
$currentPortable = Join-Path $root "dist\FreeSRT"
$existingData = Join-Path $currentPortable "data"
$stagedPortable = Join-Path $stageDist "FreeSRT"
$stagedCpuZip = Join-Path $stageRoot "FreeSRT-portable-CPU.zip"
$stagedFullZip = Join-Path $stageRoot "FreeSRT-portable.zip"
$finalCpuZip = Join-Path $root "dist\FreeSRT-portable-CPU.zip"
$finalFullZip = Join-Path $root "dist\FreeSRT-portable.zip"

New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null
try {
    Copy-PortableUserData -WorkspaceRoot $root -CurrentDataRoot $existingData -RecoveryRoot $recoveryRoot | Out-Null
    Invoke-PortableFaultPoint $TestFaultPoint "after-recovery-copy"

    $hasPyInstaller = & $python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('PyInstaller') else 1)"
    if ($LASTEXITCODE -ne 0) {
        & $python -m pip install pyinstaller
        if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller" }
    }

    & $python -m PyInstaller --noconfirm --clean --distpath $stageDist --workpath $stageWork (Join-Path $root "FreeSRT.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
    Invoke-PortableFaultPoint $TestFaultPoint "after-staged-build"

    foreach ($folder in @("models", "uploads", "outputs", "data", "gpu-runtimes")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $stagedPortable $folder) | Out-Null
    }
    Copy-Item -LiteralPath (Join-Path $root "PORTABLE_BUILD.md") -Destination (Join-Path $stagedPortable "PORTABLE_BUILD.md") -Force
    Copy-Item -LiteralPath (Join-Path $root "THIRD_PARTY_NOTICES.md") -Destination (Join-Path $stagedPortable "THIRD_PARTY_NOTICES.md") -Force
    Copy-Item -LiteralPath (Join-Path $root "licenses") -Destination (Join-Path $stagedPortable "licenses") -Recurse -Force
    Assert-PortableBinaryPolicy $stagedPortable
    Invoke-PortableFaultPoint $TestFaultPoint "after-staged-validation"

    Compress-Archive -Path (Join-Path $stagedPortable "*") -DestinationPath $stagedCpuZip -CompressionLevel Optimal

    $gpuVersion = "1.9.1-freesrt.1"
    $artifactFolder = Join-Path $root "build\gpu-artifacts"
    $cudaArchive = Join-Path $artifactFolder "whisper-cublas-11.8.0-bin-x64.zip"
    $cudaUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.1/whisper-cublas-11.8.0-bin-x64.zip"
    $cudaSha256 = "aecdce0e4d4bb758a7c72a31f3f9f19a7b6d861405fd2da743cd86398633c963"
    if (-not $VulkanRuntimeArchive) {
        $VulkanRuntimeArchive = Join-Path $artifactFolder "FreeSRT-whisper-vulkan-win-x64-$gpuVersion.zip"
    }
    New-Item -ItemType Directory -Force -Path $artifactFolder | Out-Null
    $cudaValid = (Test-Path -LiteralPath $cudaArchive -PathType Leaf) -and ((Get-FileHash -LiteralPath $cudaArchive -Algorithm SHA256).Hash.ToLowerInvariant() -eq $cudaSha256)
    if (-not $cudaValid) {
        Write-Host "Downloading official whisper.cpp CUDA 11.8 runtime..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $cudaUrl -OutFile $cudaArchive
    }
    $actualCudaHash = (Get-FileHash -LiteralPath $cudaArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualCudaHash -ne $cudaSha256) { throw "CUDA runtime checksum mismatch. Expected $cudaSha256, got $actualCudaHash" }
    if (-not (Test-Path -LiteralPath $VulkanRuntimeArchive -PathType Leaf)) {
        throw "Missing Vulkan runtime archive: $VulkanRuntimeArchive. Build it from whisper.cpp v1.9.1 with build_gpu_runtimes.ps1."
    }

    function Install-GpuRuntime([string]$Archive, [string]$Backend, [hashtable]$Manifest) {
        $runtimeRoot = Join-Path $stagedPortable "gpu-runtimes\$Backend\$gpuVersion"
        New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
        & $python -m freesrt.runtime_policy extract-runtime --archive $Archive --backend $Backend --destination $runtimeRoot
        if ($LASTEXITCODE -ne 0) { throw "$Backend runtime archive failed the shared runtime binary policy" }
        $Manifest.backend = $Backend
        $Manifest.version = $gpuVersion
        $Manifest.architecture = "win-x64"
        $Manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runtimeRoot "runtime-manifest.json") -Encoding utf8
    }

    Install-GpuRuntime $cudaArchive "cuda" @{
        source = "official whisper.cpp release"; source_url = $cudaUrl
        whisper_cpp_version = "1.9.1"; accelerator = "CUDA 11.8"; sha256 = $cudaSha256
    }
    $vulkanHash = (Get-FileHash -LiteralPath $VulkanRuntimeArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    Install-GpuRuntime $VulkanRuntimeArchive "vulkan" @{
        source = "built from official whisper.cpp source"
        source_commit = "f049fff95a089aa9969deb009cdd4892b3e74916"
        whisper_cpp_version = "1.9.1"; vulkan_sdk_version = "1.4.350.0"; sha256 = $vulkanHash
    }

    Assert-PortableBinaryPolicy $stagedPortable
    Compress-Archive -Path (Join-Path $stagedPortable "*") -DestinationPath $stagedFullZip -CompressionLevel Optimal
    Assert-PortableArchiveExcludesUserData -WorkspaceRoot $root -ArchivePath $stagedCpuZip
    Assert-PortableArchiveExcludesUserData -WorkspaceRoot $root -ArchivePath $stagedFullZip
    Invoke-PortableFaultPoint $TestFaultPoint "after-archive-creation"

    Restore-PortableUserData -WorkspaceRoot $root -RecoveryRoot $recoveryRoot -StagedDataRoot (Join-Path $stagedPortable "data")
    Invoke-PortableFaultPoint $TestFaultPoint "after-user-data-restore"

    $promotion = Invoke-PortablePromotion -WorkspaceRoot $root -BuildId $buildId `
        -CurrentPortable $currentPortable -StagedPortable $stagedPortable `
        -FinalCpuZip $finalCpuZip -StagedCpuZip $stagedCpuZip `
        -FinalFullZip $finalFullZip -StagedFullZip $stagedFullZip -FaultPoint $TestFaultPoint

    Write-Host "Portable builds ready:" -ForegroundColor Green
    Write-Host "  $($promotion.CurrentPortable)\FreeSRT.exe"
    Write-Host "  $finalFullZip (CPU + CUDA + Vulkan)"
    Write-Host "  $finalCpuZip (CPU only)"
    Write-Host "User-data recovery copy: $recoveryRoot"
    if ($promotion.PreviousPortable) { Write-Host "Previous runnable rollback: $($promotion.PreviousPortable)" }
} catch {
    Write-Warning "Portable build failed. Existing dist was not changed or was rolled back."
    Write-Warning "User-data recovery copy: $recoveryRoot"
    Write-Warning "Failed build staging: $stageRoot"
    throw
}
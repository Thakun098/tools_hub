$ErrorActionPreference = "Stop"

$pluginRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $pluginRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Missing venv; create it and install requirements-dev.txt first"
}

Push-Location $pluginRoot
try {
    & $python -m PyInstaller --clean --noconfirm .\ImageUniversalToolsEngine.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
    & .\dist\image-engine.exe probe
    if ($LASTEXITCODE -ne 0) { throw "image-engine probe failed" }
} finally {
    Pop-Location
}

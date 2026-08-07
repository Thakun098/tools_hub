Set-StrictMode -Version Latest

$script:PortableUserDataFiles = @("glossary.json", "preferences.json", "editor-backup.json")

function Get-PortableFullPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw "Path must not be empty" }
    return [System.IO.Path]::GetFullPath($Path)
}

function Assert-PathWithin([string]$Root, [string]$Path) {
    $rootFull = (Get-PortableFullPath $Root).TrimEnd([char[]]@('\', '/'))
    $pathFull = Get-PortableFullPath $Path
    $prefix = $rootFull + [System.IO.Path]::DirectorySeparatorChar
    if (-not $pathFull.Equals($rootFull, [StringComparison]::OrdinalIgnoreCase) -and
        -not $pathFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes the approved workspace root: $pathFull"
    }
    return $pathFull
}

function Invoke-PortableFaultPoint([string]$Requested, [string]$Current) {
    if ($Requested -and $Requested.Equals($Current, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Injected portable-build fault: $Current"
    }
}

function Copy-PortableUserData(
    [string]$WorkspaceRoot,
    [string]$CurrentDataRoot,
    [string]$RecoveryRoot
) {
    $current = Assert-PathWithin $WorkspaceRoot $CurrentDataRoot
    $recovery = Assert-PathWithin $WorkspaceRoot $RecoveryRoot
    New-Item -ItemType Directory -Force -Path $recovery | Out-Null
    foreach ($name in $script:PortableUserDataFiles) {
        $source = Join-Path $current $name
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $recovery $name) -Force
        }
    }
    return $recovery
}

function Restore-PortableUserData(
    [string]$WorkspaceRoot,
    [string]$RecoveryRoot,
    [string]$StagedDataRoot
) {
    $recovery = Assert-PathWithin $WorkspaceRoot $RecoveryRoot
    $staged = Assert-PathWithin $WorkspaceRoot $StagedDataRoot
    New-Item -ItemType Directory -Force -Path $staged | Out-Null
    foreach ($name in $script:PortableUserDataFiles) {
        $source = Join-Path $recovery $name
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $staged $name) -Force
        }
    }
}

function Assert-PortableArchiveExcludesUserData([string]$WorkspaceRoot, [string]$ArchivePath) {
    $archive = Assert-PathWithin $WorkspaceRoot $ArchivePath
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $personal = @(
            $zip.Entries | Where-Object {
                $normalized = $_.FullName.Replace('\', '/').ToLowerInvariant()
                foreach ($name in $script:PortableUserDataFiles) {
                    if ($normalized -eq "data/$name" -or $normalized.EndsWith("/data/$name")) { return $true }
                }
                return $false
            }
        )
        if ($personal.Count -gt 0) {
            throw "Release archive contains personal user data: $($personal.FullName -join ', ')"
        }
    } finally {
        $zip.Dispose()
    }
}

function Invoke-PortablePromotion(
    [string]$WorkspaceRoot,
    [string]$BuildId,
    [string]$CurrentPortable,
    [string]$StagedPortable,
    [string]$FinalCpuZip,
    [string]$StagedCpuZip,
    [string]$FinalFullZip,
    [string]$StagedFullZip,
    [string]$FaultPoint = ""
) {
    $current = Assert-PathWithin $WorkspaceRoot $CurrentPortable
    $staged = Assert-PathWithin $WorkspaceRoot $StagedPortable
    $finalCpu = Assert-PathWithin $WorkspaceRoot $FinalCpuZip
    $stagedCpu = Assert-PathWithin $WorkspaceRoot $StagedCpuZip
    $finalFull = Assert-PathWithin $WorkspaceRoot $FinalFullZip
    $stagedFull = Assert-PathWithin $WorkspaceRoot $StagedFullZip
    if (-not (Test-Path -LiteralPath $staged -PathType Container)) { throw "Staged portable directory is missing" }
    foreach ($archive in @($stagedCpu, $stagedFull)) {
        if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "Staged archive is missing: $archive" }
    }

    $distRoot = Split-Path -Parent $current
    $backupPortable = Join-Path $distRoot ".FreeSRT.rollback-$BuildId"
    $backupCpu = "$finalCpu.rollback-$BuildId"
    $backupFull = "$finalFull.rollback-$BuildId"
    foreach ($backup in @($backupPortable, $backupCpu, $backupFull)) {
        Assert-PathWithin $WorkspaceRoot $backup | Out-Null
        if (Test-Path -LiteralPath $backup) { throw "Rollback target already exists: $backup" }
    }

    New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
    $oldPortableMoved = $false
    $newPortableMoved = $false
    $oldCpuMoved = $false
    $newCpuMoved = $false
    $oldFullMoved = $false
    $newFullMoved = $false
    try {
        if (Test-Path -LiteralPath $current) {
            Move-Item -LiteralPath $current -Destination $backupPortable
            $oldPortableMoved = $true
        }
        Invoke-PortableFaultPoint $FaultPoint "after-old-dist-move"
        Move-Item -LiteralPath $staged -Destination $current
        $newPortableMoved = $true
        Invoke-PortableFaultPoint $FaultPoint "after-new-dist-promotion"

        if (Test-Path -LiteralPath $finalCpu) {
            Move-Item -LiteralPath $finalCpu -Destination $backupCpu
            $oldCpuMoved = $true
        }
        Move-Item -LiteralPath $stagedCpu -Destination $finalCpu
        $newCpuMoved = $true
        if (Test-Path -LiteralPath $finalFull) {
            Move-Item -LiteralPath $finalFull -Destination $backupFull
            $oldFullMoved = $true
        }
        Move-Item -LiteralPath $stagedFull -Destination $finalFull
        $newFullMoved = $true
        Invoke-PortableFaultPoint $FaultPoint "after-archive-promotion"
    } catch {
        if ($newFullMoved -and (Test-Path -LiteralPath $finalFull)) {
            Move-Item -LiteralPath $finalFull -Destination "$stagedFull.failed-promotion"
        }
        if ($oldFullMoved -and (Test-Path -LiteralPath $backupFull)) {
            Move-Item -LiteralPath $backupFull -Destination $finalFull
        }
        if ($newCpuMoved -and (Test-Path -LiteralPath $finalCpu)) {
            Move-Item -LiteralPath $finalCpu -Destination "$stagedCpu.failed-promotion"
        }
        if ($oldCpuMoved -and (Test-Path -LiteralPath $backupCpu)) {
            Move-Item -LiteralPath $backupCpu -Destination $finalCpu
        }
        if ($newPortableMoved -and (Test-Path -LiteralPath $current)) {
            Move-Item -LiteralPath $current -Destination "$staged.failed-promotion"
        }
        if ($oldPortableMoved -and (Test-Path -LiteralPath $backupPortable)) {
            Move-Item -LiteralPath $backupPortable -Destination $current
        }
        throw
    }

    return [pscustomobject]@{
        CurrentPortable = $current
        PreviousPortable = if ($oldPortableMoved) { $backupPortable } else { $null }
        PreviousCpuZip = if ($oldCpuMoved) { $backupCpu } else { $null }
        PreviousFullZip = if ($oldFullMoved) { $backupFull } else { $null }
    }
}
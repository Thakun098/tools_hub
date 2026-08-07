$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path (Split-Path -Parent $PSScriptRoot) "build_portable_helpers.ps1")

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Assert-BytesEqual([byte[]]$Expected, [byte[]]$Actual, [string]$Message) {
    if ($Expected.Length -ne $Actual.Length) { throw "ASSERTION FAILED: $Message (length)" }
    for ($index = 0; $index -lt $Expected.Length; $index++) {
        if ($Expected[$index] -ne $Actual[$index]) { throw "ASSERTION FAILED: $Message (byte $index)" }
    }
}

function New-TransactionFixture([string]$Workspace, [string]$Name) {
    $caseRoot = Join-Path $Workspace $Name
    $current = Join-Path $caseRoot "dist\FreeSRT"
    $currentData = Join-Path $current "data"
    $staged = Join-Path $caseRoot "build\stage\FreeSRT"
    $stagedData = Join-Path $staged "data"
    $recovery = Join-Path $caseRoot "build\recovery"
    New-Item -ItemType Directory -Force -Path $currentData, $stagedData | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $current "marker.txt"), "old")
    [System.IO.File]::WriteAllText((Join-Path $staged "marker.txt"), "new")
    $personal = [byte[]](0, 1, 2, 127, 128, 254, 255)
    [System.IO.File]::WriteAllBytes((Join-Path $currentData "glossary.json"), $personal)
    Copy-PortableUserData -WorkspaceRoot $caseRoot -CurrentDataRoot $currentData -RecoveryRoot $recovery | Out-Null

    $stagedCpu = Join-Path $caseRoot "build\stage\cpu.zip"
    $stagedFull = Join-Path $caseRoot "build\stage\full.zip"
    Compress-Archive -Path (Join-Path $staged "*") -DestinationPath $stagedCpu
    Compress-Archive -Path (Join-Path $staged "*") -DestinationPath $stagedFull
    Assert-PortableArchiveExcludesUserData -WorkspaceRoot $caseRoot -ArchivePath $stagedCpu
    Assert-PortableArchiveExcludesUserData -WorkspaceRoot $caseRoot -ArchivePath $stagedFull
    Restore-PortableUserData -WorkspaceRoot $caseRoot -RecoveryRoot $recovery -StagedDataRoot $stagedData

    $finalCpu = Join-Path $caseRoot "dist\FreeSRT-portable-CPU.zip"
    $finalFull = Join-Path $caseRoot "dist\FreeSRT-portable.zip"
    [System.IO.File]::WriteAllText($finalCpu, "old-cpu")
    [System.IO.File]::WriteAllText($finalFull, "old-full")
    return [pscustomobject]@{
        Root = $caseRoot; Current = $current; CurrentData = $currentData
        Staged = $staged; Recovery = $recovery; Personal = $personal
        StagedCpu = $stagedCpu; StagedFull = $stagedFull
        FinalCpu = $finalCpu; FinalFull = $finalFull
    }
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("FreeSRT-build-recovery-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
try {
    $escaped = $false
    try { Assert-PathWithin $tempRoot (Join-Path (Split-Path -Parent $tempRoot) "outside") | Out-Null } catch { $escaped = $true }
    Assert-True $escaped "workspace path escape must be rejected"

    foreach ($point in @("after-recovery-copy", "after-staged-build", "after-staged-validation", "after-archive-creation", "after-user-data-restore")) {
        $fixture = New-TransactionFixture $tempRoot ("early-" + $point)
        $threw = $false
        try { Invoke-PortableFaultPoint $point $point } catch { $threw = $true }
        Assert-True $threw "fault point $point must throw"
        Assert-True ((Get-Content -LiteralPath (Join-Path $fixture.Current "marker.txt") -Raw) -eq "old") "early fault must not change current dist"
        Assert-BytesEqual $fixture.Personal ([System.IO.File]::ReadAllBytes((Join-Path $fixture.Recovery "glossary.json"))) "recovery bytes after $point"
    }

    foreach ($point in @("after-old-dist-move", "after-new-dist-promotion", "after-archive-promotion")) {
        $fixture = New-TransactionFixture $tempRoot ("promotion-" + $point)
        $threw = $false
        try {
            Invoke-PortablePromotion -WorkspaceRoot $fixture.Root -BuildId "fault" `
                -CurrentPortable $fixture.Current -StagedPortable $fixture.Staged `
                -FinalCpuZip $fixture.FinalCpu -StagedCpuZip $fixture.StagedCpu `
                -FinalFullZip $fixture.FinalFull -StagedFullZip $fixture.StagedFull -FaultPoint $point | Out-Null
        } catch { $threw = $true }
        Assert-True $threw "promotion fault $point must throw"
        Assert-True ((Get-Content -LiteralPath (Join-Path $fixture.Current "marker.txt") -Raw) -eq "old") "promotion fault must restore old dist"
        Assert-True ((Get-Content -LiteralPath $fixture.FinalCpu -Raw) -eq "old-cpu") "promotion fault must restore CPU ZIP"
        Assert-True ((Get-Content -LiteralPath $fixture.FinalFull -Raw) -eq "old-full") "promotion fault must restore full ZIP"
        Assert-BytesEqual $fixture.Personal ([System.IO.File]::ReadAllBytes((Join-Path $fixture.Recovery "glossary.json"))) "recovery bytes after $point"
    }

    $success = New-TransactionFixture $tempRoot "success"
    $result = Invoke-PortablePromotion -WorkspaceRoot $success.Root -BuildId "success" `
        -CurrentPortable $success.Current -StagedPortable $success.Staged `
        -FinalCpuZip $success.FinalCpu -StagedCpuZip $success.StagedCpu `
        -FinalFullZip $success.FinalFull -StagedFullZip $success.StagedFull
    Assert-True ((Get-Content -LiteralPath (Join-Path $success.Current "marker.txt") -Raw) -eq "new") "successful promotion must install staged dist"
    Assert-True ((Get-Content -LiteralPath (Join-Path $result.PreviousPortable "marker.txt") -Raw) -eq "old") "successful promotion must retain rollback dist"
    Assert-BytesEqual $success.Personal ([System.IO.File]::ReadAllBytes((Join-Path $success.Current "data\glossary.json"))) "restored personal bytes"
    Assert-BytesEqual $success.Personal ([System.IO.File]::ReadAllBytes((Join-Path $success.Recovery "glossary.json"))) "durable recovery bytes"

    Write-Output "PORTABLE_RECOVERY_TESTS=PASS"
    Write-Output "FAULT_POINTS=8"
    Write-Output "TEMP_ROOT=$tempRoot"
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
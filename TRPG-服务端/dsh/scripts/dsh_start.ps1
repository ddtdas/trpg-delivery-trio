<#
.SYNOPSIS
  R2: start the DSH assistant UI and open it in a browser.
.DESCRIPTION
  DSH here is the DSH web frontend shipped at web/dist/keeper-ui (rev
  keeper-0.1.7-rc.1-static). It is embedded by the GM UI as the "DSH" panel
  (route #/dsh). This script:
    1) makes sure the TRPG server is up (starts it via ..\start.bat if needed)
    2) opens http://127.0.0.1:<port>/app/#/dsh (token appended automatically)

  Set TRPG_NO_BROWSER=1 to only print the URL.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$here = $PSScriptRoot
# $here is <serverRoot>\dsh\scripts -> go up TWO levels to reach the server root.
$serverRoot = Split-Path -Parent (Split-Path -Parent $here)
# Guard: if the layout is unexpected, fall back to the tree that holds start.bat.
if (-not (Test-Path (Join-Path $serverRoot "start.bat"))) {
    $cand = Join-Path (Split-Path -Parent $here) ".."
    Write-Host ("  [WARN] unexpected layout, serverRoot=" + $serverRoot)
} else {
    Write-Host ("  serverRoot = " + $serverRoot)
}
$runDir = Join-Path $serverRoot "run"
$portFile = Join-Path $runDir "server.port"

function Get-Port {
    if (Test-Path $portFile) {
        $v = (Get-Content -LiteralPath $portFile -Raw).Trim()
        if ($v -match "^\d+$") { return [int]$v }
    }
    return 0
}

function Test-Health([int]$p) {
    if ($p -le 0) { return $false }
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:" + $p + "/api/health") -TimeoutSec 3 -ErrorAction Stop
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

Write-Host "============================================================"
Write-Host "  TRPG DSH assistant - launcher"
Write-Host ("  server root : " + $serverRoot)
Write-Host "============================================================"

$port = Get-Port
if (-not (Test-Health $port)) {
    Write-Host ("  [1/2] server not up on port " + $port + " - starting it ...")
    $sb = Join-Path $serverRoot "start.bat"
    if (Test-Path $sb) {
        Push-Location $serverRoot
        cmd /c "start.bat" | Out-Null
        Pop-Location
    }
    for ($i = 0; $i -lt 40; $i++) {
        $port = Get-Port
        if (Test-Health $port) { break }
        Start-Sleep -Seconds 1
    }
}

if (-not (Test-Health $port)) {
    Write-Host "  [FAIL] server did not become healthy; cannot open DSH UI."
    Write-Host "         Try running start.bat in the server root first."
    exit 1
}
Write-Host ("  [1/2] server OK on port " + $port)

$url = "http://127.0.0.1:" + $port + "/app/#/dsh"
Write-Host ("  [2/2] DSH UI : " + $url)

if ($env:TRPG_NO_BROWSER -eq "1") {
    Write-Host "  (TRPG_NO_BROWSER=1 - not opening a browser)"
    exit 0
}

$openUi = Join-Path $serverRoot "scripts\open_ui.ps1"
if (Test-Path $openUi) {
    try { & powershell -NoProfile -ExecutionPolicy Bypass -File $openUi -Url ("http://127.0.0.1:" + $port + "/app/") -ServerRoot $serverRoot | Out-Null } catch { }
} else {
    try { Start-Process $url | Out-Null } catch { }
}
Write-Host "  done."
exit 0

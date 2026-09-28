<#
.SYNOPSIS
  R2: open the TRPG web UI in a browser, preferring a bundled Chrome.
.DESCRIPTION
  Priority:
    1) <tree>\browser\chrome.exe            (bundled portable Chrome)
    2) system Google Chrome (LOCALAPPDATA / Program Files / App Paths)
    3) Microsoft Edge
    4) OS default browser (Start-Process <url>)
  Chrome/Edge are launched with --app=<url> so the result is a clean
  chromeless "web UI" window rather than a normal browser tab.

  If -ServerRoot is given and the URL targets /app/, the webapp token is read
  from configs\access_config.yaml and appended as ?token=. Without it the GM UI
  shows "connection lost / reconnecting" because its WebSocket is unauthenticated.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [string]$ServerRoot = '',
    [string]$AppMode = '1'
)

$ErrorActionPreference = 'Continue'

function Add-Token([string]$u, [string]$root) {
    if (-not $root) { return $u }
    if ($u -notmatch '/app/') { return $u }
    if ($u -match 'token=') { return $u }
    $cfg = Join-Path $root 'configs\access_config.yaml'
    if (-not (Test-Path $cfg)) { return $u }
    try { $txt = [IO.File]::ReadAllText($cfg) } catch { return $u }
    $m = [regex]::Match($txt, 'webapp:[\s\S]*?token:\s*([0-9a-fA-F]{32})')
    if (-not $m.Success) { return $u }
    $sep = if ($u -match '\?') { '&' } else { '?' }
    return ($u + $sep + 'token=' + $m.Groups[1].Value)
}

function Find-Browser([string]$root) {
    $c = @()
    if ($root) { $c += (Join-Path $root 'browser\chrome.exe') }
    if ($env:LOCALAPPDATA) { $c += (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe') }
    $c += 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    $c += 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
    foreach ($p in $c) { if ($p -and (Test-Path -LiteralPath $p)) { return @{ exe = $p; kind = 'chrome' } } }
    try {
        $ap = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe' -ErrorAction Stop).'(default)'
        if ($ap -and (Test-Path -LiteralPath $ap)) { return @{ exe = $ap; kind = 'chrome' } }
    } catch { }
    $e = @()
    if ($env:LOCALAPPDATA) { $e += (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\Application\msedge.exe') }
    $e += 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    $e += 'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
    foreach ($p in $e) { if ($p -and (Test-Path -LiteralPath $p)) { return @{ exe = $p; kind = 'edge' } } }
    return $null
}

$target = Add-Token $Url $ServerRoot
$b = Find-Browser $ServerRoot

if ($b) {
    $bargs = @()
    if ($AppMode -eq '1') {
        $bargs += ('--app=' + $target)
        $bargs += '--new-window'
    } else {
        $bargs += $target
    }
    $bargs += '--no-first-run'
    $bargs += '--no-default-browser-check'
    try {
        Start-Process -FilePath $b.exe -ArgumentList $bargs -ErrorAction Stop | Out-Null
        Write-Host ('  [UI] opened with ' + $b.kind + ': ' + $target)
        exit 0
    } catch {
        Write-Host ('  [UI] failed to launch ' + $b.kind + ': ' + $_.Exception.Message)
    }
}

try {
    Start-Process $target | Out-Null
    Write-Host ('  [UI] opened with system default browser: ' + $target)
    exit 0
} catch {
    Write-Host ('  [UI] cannot open browser automatically, please visit: ' + $target)
    exit 1
}

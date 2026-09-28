<#
.SYNOPSIS
  R2 atomic dist deployment for the GM front end (web/dist).

.DESCRIPTION
  Problem this solves
  -------------------
  A per-file deployment (copy assets, then copy index.html, then delete stale
  hashes) leaves a window in which dist/index.html references a bundle that is
  not yet on disk. During that window the GM page is served (HTTP 200 for the
  html) but its bundle 404s -> white screen. This was observed in practice.

  Strategy
  --------
  Stage a COMPLETE dist.new next to dist, then swap by directory rename:

      dist  ->  dist.old
      dist.new -> dist
      delete dist.old

  dist.new is assembled from the authoritative web/ tree and MUST contain
  keeper-ui/ as well (a bare "vite build" would omit it; swapping in a dist
  without keeper-ui turns a short white screen into a permanent one).

  Honest limitation
  -----------------
  Windows cannot atomically rename-overwrite a non-empty directory, so a very
  short window still exists (order of milliseconds, versus seconds for
  per-file copy). True zero-window requires versioned URLs or a reverse proxy,
  which is outside this script's scope. Therefore the invariants are re-checked
  immediately after the swap and the swap is ROLLED BACK automatically if they
  fail -- atomicity reduces the chance of a window, it does not remove the
  chance of shipping wrong content.

.PARAMETER SourceWeb
  The web/ tree that provides dist/assets + dist/index.html (default: ../web).

.PARAMETER DryRun
  Assemble and validate dist.new, print the plan, but do NOT swap.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\r2_deploy_dist.ps1 -DryRun
#>
[CmdletBinding()]
param(
  [string]$SourceWeb,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $SourceWeb) { $SourceWeb = Join-Path $root 'web' }

$dist    = Join-Path $SourceWeb 'dist'
$src     = Join-Path $SourceWeb 'dist'          # assets+index.html come from the built dist
$keeper  = Join-Path $dist 'keeper-ui'
$new     = Join-Path $SourceWeb 'dist.new'
$old     = Join-Path $SourceWeb 'dist.old'
$inv     = Join-Path $PSScriptRoot 'r2_dist_integrity.ps1'

function Fail($m) { Write-Host ("FAIL  " + $m); exit 1 }
function Step($m) { Write-Host ("  ..    " + $m) }

if (-not (Test-Path -LiteralPath $dist)) { Fail "source dist not found: $dist" }
if (-not (Test-Path -LiteralPath (Join-Path $dist 'index.html'))) { Fail "dist/index.html missing" }
if (-not (Test-Path -LiteralPath $keeper)) { Fail "keeper-ui missing from dist -- refusing to build dist.new without it" }
$keeperCount = @(Get-ChildItem -LiteralPath $keeper -Recurse -File).Count
if ($keeperCount -le 0) { Fail "keeper-ui is empty -- refusing to proceed" }
Step ("keeper-ui present: {0} files" -f $keeperCount)

# ---- 1. stage a COMPLETE dist.new -------------------------------------------
if (Test-Path -LiteralPath $new) { Remove-Item -LiteralPath $new -Recurse -Force }
Step "assembling dist.new"
robocopy $dist $new /E /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "robocopy failed ($LASTEXITCODE)" }

$newKeeper = @(Get-ChildItem -LiteralPath (Join-Path $new 'keeper-ui') -Recurse -File -ErrorAction SilentlyContinue).Count
if ($newKeeper -ne $keeperCount) { Fail ("dist.new keeper-ui mismatch: {0} vs {1}" -f $newKeeper, $keeperCount) }
Step ("dist.new assembled with keeper-ui {0} files" -f $newKeeper)

# ---- 2. swap -----------------------------------------------------------------
if ($DryRun) {
  Write-Host ""
  Write-Host "DRYRUN: would now execute"
  Write-Host ("  Rename-Item {0} -> {1}" -f $dist, $old)
  Write-Host ("  Rename-Item {0} -> {1}" -f $new,  $dist)
  Write-Host ("  Remove-Item {0} -Recurse -Force" -f $old)
  Write-Host "  then re-run r2_dist_integrity.ps1 and roll back on failure"
  Step "dry-run cleanup: removing staged dist.new"
  Remove-Item -LiteralPath $new -Recurse -Force
  exit 0
}

if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force }
Step "renaming dist -> dist.old"
Rename-Item -LiteralPath $dist -NewName 'dist.old'
Step "renaming dist.new -> dist"
try {
  Rename-Item -LiteralPath $new -NewName 'dist'
} catch {
  # roll back immediately: the live dist is currently missing
  Rename-Item -LiteralPath $old -NewName 'dist'
  Fail ("swap failed, rolled back: " + $_.Exception.Message)
}

# ---- 3. verify, roll back on failure ----------------------------------------
Step "verifying invariants after swap"
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File $inv -Root $root 2>&1
$txt = ($out | Out-String)
$txt.Split("`n") | Where-Object { $_ -match '^(PASS|FAIL|RESULT)' } | ForEach-Object { Write-Host ("  " + $_.Trim()) }
if ($txt -notmatch 'ALL INVARIANTS HOLD') {
  Write-Host "INVARIANTS FAILED -- rolling back"
  Remove-Item -LiteralPath $dist -Recurse -Force
  Rename-Item -LiteralPath $old -NewName 'dist'
  Fail "rolled back to previous dist"
}

Remove-Item -LiteralPath $old -Recurse -Force
Write-Host ""
Write-Host "OK: atomic swap complete, invariants hold, dist.old removed"
exit 0

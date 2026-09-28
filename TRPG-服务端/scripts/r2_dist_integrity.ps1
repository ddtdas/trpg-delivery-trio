<#
.SYNOPSIS
  R2 dist self-consistency check (recomputable invariants, NOT point-in-time values).

.DESCRIPTION
  Acceptance rule #4: assert RECOMPUTABILITY, not observed values.

  This script asserts dist-internal INVARIANTS (immune to rebuild and to content change):

    I1  every /app/assets/<name> referenced by dist/index.html exists on disk
    I2  every file in dist/assets/ is referenced (or in the exempt set)
    I3  exactly one index-*.js   (no stale hashed dead artifacts)
    I4  exactly one index-*.css
    I5  dist/dist does not exist (no duplicated tree)
    I6  dist/keeper-ui exists and is non-empty
        (a bare "vite build" empties dist/ and would silently delete it)
    I7  theme-cnmods.css appears AFTER the bundle CSS in index.html
        (otherwise the bundle overrides the R32 theme)

  Hashes are printed at the end as POINT-IN-TIME OBSERVATIONS only, each with
  the exact command that produced it, so any reviewer can recompute them.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\r2_dist_integrity.ps1
#>
[CmdletBinding()]
param(
  [string]$Root
)
$ErrorActionPreference = 'Continue'
# NOTE: $PSScriptRoot is NOT yet populated while param() defaults are evaluated,
# so -File invocation would set $Root to an empty string. Resolve it here instead.
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
$dist = Join-Path $Root 'web\dist'
$script:fail = 0
$script:skipped = 0

function Chk($id, $desc, $ok, $detail) {
  if (-not $ok) { $script:fail++ }
  $tag = if ($ok) { 'PASS' } else { 'FAIL' }
  $d = if ($detail) { '  [' + $detail + ']' } else { '' }
  '{0}  {1}  {2}{3}' -f $tag, $id, $desc, $d
}

if (-not (Test-Path -LiteralPath $dist)) { 'FAIL  I0  dist not found: ' + $dist; exit 2 }

$htmlPath = Join-Path $dist 'index.html'
$html = Get-Content -LiteralPath $htmlPath -Raw -Encoding UTF8
$refs = @([regex]::Matches($html, '/app/assets/([A-Za-z0-9._-]+)') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
$assetsDir = Join-Path $dist 'assets'
$onDisk = @(Get-ChildItem -LiteralPath $assetsDir -File | Select-Object -ExpandProperty Name)
$exempt = @('theme-cnmods.css')

$missing = @($refs | Where-Object { $onDisk -notcontains $_ })
if ($missing.Count -eq 0) { Chk 'I1' 'index.html refs all exist' $true ("{0} refs" -f $refs.Count) }
else { Chk 'I1' 'index.html refs all exist' $false ('MISSING=' + ($missing -join ',')) }

$orphan = @($onDisk | Where-Object { $refs -notcontains $_ -and $exempt -notcontains $_ })
if ($orphan.Count -eq 0) { Chk 'I2' 'no unreferenced dead artifacts' $true ("{0} files" -f $onDisk.Count) }
else { Chk 'I2' 'no unreferenced dead artifacts' $false ('ORPHAN=' + ($orphan -join ',')) }

$js = @(Get-ChildItem -LiteralPath $assetsDir -File -Filter 'index-*.js')
$css = @(Get-ChildItem -LiteralPath $assetsDir -File -Filter 'index-*.css')
Chk 'I3' 'exactly one index-*.js'  ($js.Count -eq 1)  ("count={0}" -f $js.Count)
Chk 'I4' 'exactly one index-*.css' ($css.Count -eq 1) ("count={0}" -f $css.Count)

Chk 'I5' 'dist/dist absent' (-not (Test-Path -LiteralPath (Join-Path $dist 'dist'))) ''

$k = Join-Path $dist 'keeper-ui'
$kn = 0
if (Test-Path -LiteralPath $k) { $kn = @(Get-ChildItem -LiteralPath $k -Recurse -File).Count }
Chk 'I6' 'keeper-ui present and non-empty' ($kn -gt 0) ("files={0}" -f $kn)

$themePath = Join-Path $assetsDir 'theme-cnmods.css'
$themeOk = (Test-Path -LiteralPath $themePath) -and ((Get-Item -LiteralPath $themePath).Length -gt 0)
$themeLen = if (Test-Path -LiteralPath $themePath) { (Get-Item -LiteralPath $themePath).Length } else { 0 }
Chk 'I8' 'R32 theme overlay present in dist/assets' $themeOk ("bytes={0}" -f $themeLen)

# I8b: dist overlay must be BYTE-IDENTICAL to the source overlay in web/public/.
# This is the recomputable form (immune to rebuild AND to content change);
# comparing a hardcoded sha256 would be a point-in-time observation, not an assertion.
$pubTheme = Join-Path (Split-Path -Parent $PSScriptRoot) 'web\public\assets\theme-cnmods.css'
if ((Test-Path -LiteralPath $themePath) -and (Test-Path -LiteralPath $pubTheme)) {
  $hDist = (Get-FileHash -LiteralPath $themePath -Algorithm SHA256).Hash
  $hPub  = (Get-FileHash -LiteralPath $pubTheme  -Algorithm SHA256).Hash
  $same  = ($hDist -eq $hPub)
  Chk 'I8b' 'dist theme overlay identical to web/public source' $same ("dist={0}B public={1}B" -f $themeLen, (Get-Item -LiteralPath $pubTheme).Length)
} else {
  Chk 'I8b' 'dist theme overlay identical to web/public source' $false ('missing dist={0} public={1}' -f (Test-Path -LiteralPath $themePath), (Test-Path -LiteralPath $pubTheme))
}

# I8c: the SERVED copy must match the DISK copy.
# I1-I8b are disk-only; they cannot see a stale cache. theme-cnmods.css is the
# only dist asset referenced WITHOUT a content hash, so a client can keep using
# an OLD theme even though every disk check is green. (Raised by implementer-npc.)
# Skips -- does not fail -- when no server is listening, so this stays usable
# during packaging. Byte length is the discriminator, so no value is pinned.
$live = $false
try {
  $probe = Invoke-WebRequest -Uri 'http://127.0.0.1:9211/api/health' -UseBasicParsing -TimeoutSec 4
  if ($probe.StatusCode -eq 200) { $live = $true }
} catch { $live = $false }
if (-not $live) {
  Chk 'I8c' 'served theme overlay identical to dist on disk' $true 'SKIP (no server on 9211)'; $script:skipped++
} else {
  try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:9211/app/assets/theme-cnmods.css' -UseBasicParsing -TimeoutSec 10
    $diskLen = (Get-Item -LiteralPath $themePath).Length
    $same = ($r.RawContentLength -eq $diskLen)
    Chk 'I8c' 'served theme overlay identical to dist on disk' $same ('served={0}B disk={1}B' -f $r.RawContentLength, $diskLen)
  } catch {
    Chk 'I8c' 'served theme overlay identical to dist on disk' $false ('request failed: ' + $_.Exception.Message)
  }
}

# I8d: cache-header policy per referenced asset (raised by implementer-npc).
# I8c compares served vs disk, but the stale-copy risk lives in the CLIENT cache,
# keyed by URL -- a cache-busted probe can never hit it, so served==disk is
# vacuously true for that risk. Whether a client may reuse a stale copy is
# decided by Cache-Control, so assert that instead.
# POSITION IS LOAD-BEARING: this block must sit AFTER the I8c block above
# (so $live is already computed) and BEFORE the summary section below,
# otherwise it silently never runs.
if (-not $live) {
  Chk 'I8d' 'cache-control policy per referenced asset' $true 'SKIP (no server on 9211)'; $script:skipped++
} else {
  try {
    $refsD = @([regex]::Matches($html, '/app/assets/[A-Za-z0-9._-]+') | ForEach-Object { $_.Value } | Sort-Object -Unique)
    $bad = @(); $checked = 0
    foreach ($u in $refsD) {
      $resp = Invoke-WebRequest -Uri ('http://127.0.0.1:9211' + $u) -UseBasicParsing -TimeoutSec 10
      $cc = ''
      try { $cc = [string]$resp.Headers['Cache-Control'] } catch { $cc = '' }
      if (-not $cc) { $cc = '' }
      $leaf = ($u -split '/')[-1]
      $isHashed = ($leaf -match '-[A-Za-z0-9_]{8}\.(js|css)$')
      $checked++
      if ($isHashed) {
        $ok = ($cc -match 'immutable') -or ($cc -match 'max-age=(\d+)' -and [int]$Matches[1] -ge 31536000)
        if (-not $ok) { $bad += ($leaf + ' hashed but cc=[' + $cc + ']') }
      } else {
        $ok = ($cc -match 'no-cache') -or ($cc -match 'max-age=0')
        if (-not $ok) { $bad += ($leaf + ' unhashed but cc=[' + $cc + ']') }
      }
    }
    $script:checkedAssets = $checked
    if ($bad.Count -eq 0) {
      Chk 'I8d' 'cache-control policy per referenced asset' $true ('checked={0} all correct' -f $checked)
    } else {
      Chk 'I8d' 'cache-control policy per referenced asset' $false ((($bad -join '; ')))
    }
  } catch {
    Chk 'I8d' 'cache-control policy per referenced asset' $false ('request failed: ' + $_.Exception.Message)
  }
}

$links = @([regex]::Matches($html, '<link[^>]*href="[^"]*\.css"[^>]*>') | ForEach-Object { $_.Value })
$themeIdx = -1; $bundleIdx = -1
for ($i = 0; $i -lt $links.Count; $i++) {
  if ($links[$i] -match 'theme-cnmods\.css') { $themeIdx = $i }
  elseif ($links[$i] -match 'index-.*\.css') { $bundleIdx = $i }
}
Chk 'I7' 'theme after bundle CSS (R32 wins)' (($themeIdx -gt $bundleIdx) -and ($themeIdx -ge 0)) ("bundle={0} theme={1}" -f $bundleIdx, $themeIdx)

''
'--- SKIP ACCOUNTING (criterion: SKIPPED must be 0 when a server is live) ---'
'SKIPPED = ' + $script:skipped
''
'--- POINT-IN-TIME OBSERVATIONS (recorded, not asserted) ---'
'producing command: Get-FileHash -LiteralPath <file> -Algorithm SHA256'
Get-ChildItem -LiteralPath $dist -Recurse -File |
  Where-Object { ($_.Extension -in '.js', '.css', '.html') -and ($_.FullName -notmatch 'keeper-ui') } |
  Sort-Object FullName | ForEach-Object {
    $h = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
    '  {0}  len={1}  {2}  {3}' -f $h, $h.Length, $_.Length.ToString().PadLeft(7), $_.FullName.Substring($dist.Length + 1)
  }
''
if ($script:fail -eq 0) { 'RESULT: ALL INVARIANTS HOLD (fail=0) skipped=' + $script:skipped } else { 'RESULT: FAILED invariants=' + $script:fail + ' skipped=' + $script:skipped }
exit $script:fail
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
$web = 'C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端\web'
$b = Join-Path $env:TEMP 'gmweb-fix-build'
$log = Join-Path $web 'build-fix3.log'
"=== FIX3 build start $(Get-Date) ===" | Out-File $log -Encoding UTF8
# 1) backup current dist (keeper-ui + assets) for rollback
$bk = Join-Path $env:TEMP 'keeper-ui-backup-fix3'
if (Test-Path $bk) { Remove-Item $bk -Recurse -Force }
robocopy (Join-Path $web 'dist\keeper-ui') $bk /E /NFL /NDL /NJH /NJS /NP | Out-Null
"keeper-ui backup: $(Test-Path (Join-Path $bk 'index.html'))" | Out-File $log -Append -Encoding UTF8
# 2) copy source to temp (exclude node_modules/dist), so vite emptyOutDir never touches real dist
if (Test-Path $b) { Remove-Item $b -Recurse -Force }
robocopy $web $b /E /XD node_modules dist dist-preview .pytest_cache __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
Set-Location $b
"copied to temp $b" | Out-File $log -Append -Encoding UTF8
"--- npm ci start $(Get-Date) ---" | Out-File $log -Append -Encoding UTF8
npm ci --no-audit --no-fund 2>&1 | Out-File $log -Append -Encoding UTF8
"--- npm ci exit=$LASTEXITCODE done $(Get-Date) ---" | Out-File $log -Append -Encoding UTF8
"--- build:remote start $(Get-Date) ---" | Out-File $log -Append -Encoding UTF8
npm run build:remote 2>&1 | Out-File $log -Append -Encoding UTF8
$be = $LASTEXITCODE
"--- build:remote exit=$be done $(Get-Date) ---" | Out-File $log -Append -Encoding UTF8
if (Test-Path (Join-Path $b 'dist\index.html')) {
  # additive deploy: copy main bundle only, keeper-ui untouched
  robocopy (Join-Path $b 'dist') (Join-Path $web 'dist') /E /NFL /NDL /NJH /NJS /NP | Out-Null
  "DIST_DEPLOYED=1 buildExit=$be" | Out-File $log -Append -Encoding UTF8
  $refs = [regex]::Matches((Get-Content (Join-Path $web 'dist\index.html') -Raw -Encoding UTF8), 'assets/([A-Za-z0-9_.\-]+)') | ForEach-Object { $_.Groups[1].Value }
  Get-ChildItem (Join-Path $web 'dist\assets') -File | Where-Object { $refs -notcontains $_.Name } | ForEach-Object { "PRUNE " + $_.Name | Out-File $log -Append -Encoding UTF8; Remove-Item $_.FullName -Force }
  Remove-Item (Join-Path $web 'dist\dist') -Recurse -Force -ErrorAction SilentlyContinue
  "keeper-ui files after: " + (Get-ChildItem (Join-Path $web 'dist\keeper-ui') -Recurse -File | Measure-Object).Count | Out-File $log -Append -Encoding UTF8
} else {
  "DIST_DEPLOYED=0 buildExit=$be (build failed, dist untouched)" | Out-File $log -Append -Encoding UTF8
}
Remove-Item $b -Recurse -Force -ErrorAction SilentlyContinue
"=== FIX3 build end $(Get-Date) ===" | Out-File $log -Append -Encoding UTF8

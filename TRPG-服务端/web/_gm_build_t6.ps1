
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
$web = 'C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端\web'
$b = Join-Path $env:TEMP 'gmweb-build'
$log = Join-Path $web 'build-t6.log'
"=== T6 GM build start $(Get-Date) ===" | Out-File $log -Encoding UTF8
$kb = Join-Path $env:TEMP 'keeper-ui-backup-t6'
if (Test-Path $kb) { Remove-Item $kb -Recurse -Force }
robocopy (Join-Path $web 'dist\keeper-ui') $kb /E /NFL /NDL /NJH /NJS /NP | Out-Null
"keeper-ui backed up: $(Test-Path (Join-Path $kb 'index.html'))" | Out-File $log -Append -Encoding UTF8
if (Test-Path $b) { Remove-Item $b -Recurse -Force }
robocopy $web $b /E /XD node_modules dist dist-preview .pytest_cache __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
Set-Location $b
"copied to temp" | Out-File $log -Append -Encoding UTF8
"--- npm ci start $(Get-Date) ---" | Out-File $log -Append -Encoding UTF8
npm ci --no-audit --no-fund 2>&1 | Out-File $log -Append -Encoding UTF8
"--- npm ci done $(Get-Date) ---" | Out-File $log -Append -Encoding UTF8
npm run build:remote 2>&1 | Out-File $log -Append -Encoding UTF8
"--- build done $(Get-Date) ---" | Out-File $log -Append -Encoding UTF8
if (Test-Path (Join-Path $b 'dist\index.html')) {
  robocopy (Join-Path $b 'dist') (Join-Path $web 'dist') /E /NFL /NDL /NJH /NJS /NP | Out-Null
  robocopy $kb (Join-Path $web 'dist\keeper-ui') /E /NFL /NDL /NJH /NJS /NP | Out-Null
  "DIST_DEPLOYED=1" | Out-File $log -Append -Encoding UTF8
  $refs = [regex]::Matches((Get-Content (Join-Path $web 'dist\index.html') -Raw -Encoding UTF8), 'assets/([A-Za-z0-9_.\-]+)') | ForEach-Object { $_.Groups[1].Value }
  Get-ChildItem (Join-Path $web 'dist\assets') -File | Where-Object { $refs -notcontains $_.Name } | Remove-Item -Force
  Remove-Item (Join-Path $web 'dist\dist') -Recurse -Force -ErrorAction SilentlyContinue
} else {
  "DIST_DEPLOYED=0 (build failed)" | Out-File $log -Append -Encoding UTF8
}
Remove-Item $b -Recurse -Force -ErrorAction SilentlyContinue
"=== T6 GM build end $(Get-Date) ===" | Out-File $log -Append -Encoding UTF8

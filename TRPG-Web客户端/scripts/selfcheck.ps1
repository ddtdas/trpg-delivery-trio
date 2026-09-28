<#
.SYNOPSIS
    TRPG Web 客户端 —— 解压后自检。

.DESCRIPTION
    逐项检查并在最后输出一行结论：
      · Python 是否存在且 >= 3.12
      · client\ 6 个本体文件是否齐全
      · 8080-8090 端口区间是否至少有一个空闲端口
      · 能否连上服务端（读 ..\TRPG-服务端\run\server.json；未启动记为 WARN）
      · 本客户端是否已在运行
    结论行：自检结果：PASS / 自检结果：FAIL
    退出码：0 = PASS，1 = FAIL
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'

$ScriptDir = $PSScriptRoot
$RepoRoot  = Split-Path -Parent $ScriptDir
$ClientDir = Join-Path $RepoRoot 'client'
$RunDir    = Join-Path $RepoRoot 'run'

$PortLow  = 8080
$PortHigh = 8090

$script:Failed = 0
$script:Warned = 0

function Write-Step([string]$m) { Write-Host ('  ' + $m) }
function Write-Ok([string]$m)   { Write-Host ('  [OK]   ' + $m) -ForegroundColor Green }
function Write-Warn2([string]$m){ Write-Host ('  [WARN] ' + $m) -ForegroundColor Yellow; $script:Warned++ }
function Write-Fail([string]$m) { Write-Host ('  [FAIL] ' + $m) -ForegroundColor Red;    $script:Failed++ }

Write-Host ''
Write-Host 'TRPG Web 客户端 —— 自检' -ForegroundColor Cyan
Write-Host '============================================'
Write-Host ('  目录：' + $RepoRoot)
Write-Host ('  时刻：' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host ''

# ---- 1. Python ------------------------------------------------------------
Write-Host '[1/5] Python 环境'
$py = $null
$cmd = Get-Command python -ErrorAction SilentlyContinue
if ($cmd) { $py = $cmd.Source }
else {
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py) {
    Write-Fail '未找到 python / py 命令。请安装 Python 3.12+ 并勾选 Add python.exe to PATH。'
} else {
    # 只取「含版本号的那一行」：某些 Python 发行版会在 -c 时向 stdout 多吐一行
    # （发行版 banner / sitecustomize.py），那样 $verText 会变成数组，
    # 直接 [version] 转换会抛未捕获异常，脚本会崩而不是给出中文 FAIL。
    $verRaw  = & $py -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
    $verText = ''
    if ($verRaw) {
        $vc = @($verRaw) | Where-Object { $_ -match '^\s*\d+\.\d+' } | Select-Object -Last 1
        if ($vc) { $verText = $vc.ToString().Trim() }
    }
    if ($LASTEXITCODE -ne 0 -or -not $verText) {
        Write-Fail ('python 存在但无法执行或版本号无法解析：' + $py)
    } else {
        $mm = $null
        try { $mm = [version]($verText -replace '^(\d+\.\d+).*$', '$1') } catch { $mm = $null }
        if (-not $mm) {
            Write-Fail ('无法解析 Python 版本号（原始输出：' + $verText + '）。请确认 python 可正常执行。')
        } elseif ($mm -lt [version]'3.12') {
            Write-Fail ('Python 版本过低：' + $verText + '（需要 3.12+）')
        } else {
            Write-Ok ('Python ' + $verText + '  ->  ' + $py)
        }
    }
}
Write-Host ''

# ---- 2. client/ 本体文件 --------------------------------------------------
Write-Host '[2/5] 客户端本体文件（client\ 6 个）'
$need = @('index.html','app.js','app.css','strings.json','tokens.json','README.md')
$missing = @()
foreach ($f in $need) {
    $p = Join-Path $ClientDir $f
    if (Test-Path $p) {
        $sz = (Get-Item $p).Length
        Write-Step ('  [OK] ' + $f + '  (' + $sz + ' 字节)')
    } else {
        $missing += $f
    }
}
if ($missing.Count -gt 0) {
    Write-Fail ('client\ 缺少 ' + $missing.Count + ' 个文件：' + ($missing -join ', '))
} else {
    Write-Ok 'client\ 6 个文件齐全。'
}
foreach ($s in @('scripts\serve.py','scripts\start.ps1','scripts\stop.ps1','start.bat','stop.bat')) {
    $p = Join-Path $RepoRoot $s
    if (-not (Test-Path $p)) { Write-Fail ('缺少 ' + $s) }
}
Write-Host ''

# ---- 3. 端口区间 ----------------------------------------------------------
Write-Host ('[3/5] 端口区间 ' + $PortLow + '-' + $PortHigh)
function Test-PortFree([int]$p) {
    try {
        $hit = netstat -ano | Select-String -SimpleMatch -Pattern (':' + $p + ' ') -ErrorAction SilentlyContinue |
               Where-Object { $_.Line -match 'LISTENING' } | Select-Object -First 1
        if ($hit) { return $false }
    } catch { }
    $l = $null
    try {
        $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $p)
        $l.Start()
        return $true
    } catch { return $false } finally { if ($l) { try { $l.Stop() } catch { } } }
}
$freeCount = 0
$busyList  = @()
foreach ($p in $PortLow..$PortHigh) {
    if (Test-PortFree $p) { $freeCount++ } else { $busyList += $p }
}
if ($freeCount -gt 0) {
    Write-Ok ('空闲 ' + $freeCount + ' / ' + ($PortHigh - $PortLow + 1) + ' 个端口可用。')
} else {
    Write-Fail ('端口 ' + $PortLow + '-' + $PortHigh + ' 全部被占用，无法启动。')
}
if ($busyList.Count -gt 0) { Write-Step ('  已占用：' + ($busyList -join ', ')) }
Write-Host ''

# ---- 4. 是否已在运行 ------------------------------------------------------
Write-Host '[4/5] 本客户端运行状态'
$running = @()
foreach ($p in $PortLow..$PortHigh) {
    try {
        $r = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $p + '/__trpg_client__') -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200 -and $r.Content.Contains('trpg-client')) { $running += $p }
    } catch { }
}
if ($running.Count -gt 0) {
    Write-Ok ('已在运行，端口：' + ($running -join ', '))
    foreach ($p in $running) { Write-Step ('  地址：http://127.0.0.1:' + $p + '/index.html') }
} else {
    Write-Step '  未检测到运行中的本客户端（正常，双击 start.bat 启动）。'
}
Write-Host ''

# ---- 5. 服务端连通性 ------------------------------------------------------
Write-Host '[5/5] 服务端连通性'
$SiblingRoot = Split-Path -Parent $RepoRoot
$serverJson  = ''
$siblingDir  = ''
$siblingName = ''
# 两个候选名取并集：TRPG-服务端 = 交付包解压后的目录名（主路径）；trpg-server = 开发树名（备用路径）。
# $siblingDir 记录「任一候选目录存在」，$serverJson 记录「任一候选里有发现文件」—— 两者独立判定，
# 否则用户把包解压成 trpg-server 时会被错判为「两包不在同一父目录」。
foreach ($name in @('TRPG-服务端', 'trpg-server')) {
    $dir  = Join-Path $SiblingRoot $name
    $cand = Join-Path (Join-Path $dir 'run') 'server.json'
    if (Test-Path $cand) { $serverJson = $cand; $siblingDir = $dir; $siblingName = $name; break }
    if ((-not $siblingDir) -and (Test-Path $dir)) { $siblingDir = $dir; $siblingName = $name }
}
if (-not $serverJson -and $siblingDir) {
    # 分支2：目录在、发现文件不在 -> 服务端没在运行（run\server.json 只在运行期间存在）
    Write-Warn2 ('找到同级服务端目录 ..\' + $siblingName + '，但其中没有 run\server.json。')
    Write-Step  '  这说明【服务端当前没有在运行】：run\server.json 只在服务端运行期间存在，'
    Write-Step  '  stop.bat 停止后会删除它（日志保留）。'
    Write-Step  ('  请先双击 ..\' + $siblingName + '\start.bat 启动服务端，再重跑本自检。')
} elseif (-not $serverJson) {
    # 分支3：两个候选目录都不存在 -> 布局问题
    Write-Warn2 '同级目录下没有找到服务端（..\TRPG-服务端 与 ..\trpg-server 都不存在）。'
    Write-Step  '  这说明【两个包没有解压到同一个父目录】。'
    Write-Step  '  建议：把两个 zip 解压到同一父目录后重试；'
    Write-Step  '  或显式指定地址：start.bat 8080 http://<服务端IP>:<端口>'
} else {
    Write-Step ('  发现文件：' + $serverJson)
    $surl = ''
    try {
        $sj = Get-Content $serverJson -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([int]$sj.port -gt 0) { $surl = 'http://127.0.0.1:' + [int]$sj.port }
    } catch { }
    if (-not $surl) {
        Write-Warn2 '服务端发现文件存在但无法解析出端口。'
    } else {
        Write-Step ('  服务端地址：' + $surl)
        $ok = $false
        try {
            $hr = Invoke-WebRequest -Uri ($surl + '/api/health') -UseBasicParsing -TimeoutSec 5
            if ($hr.StatusCode -eq 200) { $ok = $true }
        } catch { }
        if ($ok) { Write-Ok ('服务端可达：' + $surl + '/api/health -> 200') }
        else     { Write-Warn2 ('服务端不可达：' + $surl + '（请先启动 TRPG-服务端\start.bat）') }
    }
}
Write-Host ''

# ---- 结论 ----------------------------------------------------------------
Write-Host '============================================'
if ($script:Failed -eq 0) {
    Write-Host '  自检结果：PASS' -ForegroundColor Green
    if ($script:Warned -gt 0) { Write-Host ('  （有 ' + $script:Warned + ' 项 WARN，不影响客户端本身可用）') -ForegroundColor Yellow }
    Write-Host ''
    exit 0
} else {
    Write-Host ('  自检结果：FAIL（' + $script:Failed + ' 项失败）') -ForegroundColor Red
    Write-Host ''
    exit 1
}
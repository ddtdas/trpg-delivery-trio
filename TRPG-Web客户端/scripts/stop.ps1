<#
.SYNOPSIS
    TRPG 客户端 —— 停止本地静态服务器。

.DESCRIPTION
    定位顺序（宁可多查一层，也不留孤儿进程）：
      1) run/client.json 里本服务自己记录的 pid（最可靠），并校验该进程确实是 serve.py；
      2) 按 run/client.port 指定的端口反查监听进程（Get-NetTCPConnection，失败则回退 netstat）。
    找到后优雅停止 -> 确认端口已释放 -> 删除 run/client.port 与 run/client.json（保留日志）。

    退出码：0 成功（或本来就没在运行）| 1 停止失败/端口仍被占用

.PARAMETER Port
    可选。显式指定端口，覆盖 run/client.port。
#>
[CmdletBinding()]
param(
    [int]$Port = 0
)

$ErrorActionPreference = 'Stop'

$EXIT_OK  = 0
$EXIT_ENV = 1

$ScriptDir = $PSScriptRoot
$RepoRoot  = Split-Path -Parent $ScriptDir
$RunDir    = Join-Path $RepoRoot 'run'
$PortFile  = Join-Path $RunDir 'client.port'
$JsonFile  = Join-Path $RunDir 'client.json'

function Write-Step([string]$msg) { Write-Host ('  ' + $msg) }
function Write-Ok([string]$msg)   { Write-Host ('  [OK]   ' + $msg) -ForegroundColor Green }
function Write-Warn2([string]$msg){ Write-Host ('  [WARN] ' + $msg) -ForegroundColor Yellow }
function Write-Fail([string]$msg) { Write-Host ('  [FAIL] ' + $msg) -ForegroundColor Red }

function Test-PortFree([int]$p) {
    # 判据 1（**权威**）：netstat -ano 看该端口有没有 LISTENING。
    # 为什么不能拿试绑当权威：Windows 的 SO_REUSEADDR 允许在已有监听者之上再绑定 ——
    # 实测占用者绑 0.0.0.0 且设 SO_REUSEADDR 时，TcpListener(127.0.0.1,p).Start() 仍会成功，
    # 所以「试绑成功」不等于「端口空闲」。（占用者未设 SO_REUSEADDR 时试绑仍能正确判占用。）
    try {
        $hit = netstat -ano | Select-String -SimpleMatch -Pattern (':' + $p + ' ') -ErrorAction SilentlyContinue |
               Where-Object { $_.Line -match 'LISTENING' } | Select-Object -First 1
        if ($hit) { return $false }
    } catch { }
    # 判据 2（兜底）：试绑回环端口；绑不上 = 被占用（这个方向是可信的）
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $p)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) { try { $listener.Stop() } catch { } }
    }
}

# 该 pid 是否为本客户端的 serve.py？(避免误杀别的进程)
function Test-IsOurServe([int]$procId) {
    if ($procId -le 0) { return $false }
    try {
        $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $procId) -ErrorAction Stop
        if ($p -and $p.CommandLine -and $p.CommandLine.Contains('serve.py')) { return $true }
    } catch { }
    return $false
}

# 按端口反查监听 pid：Get-NetTCPConnection 优先，失败回退 netstat
function Get-PortOwnerPid([int]$p) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction Stop |
                Select-Object -First 1
        if ($conn) { return [int]$conn.OwningProcess }
    } catch { }
    try {
        $needle = ':' + $p + ' '
        $hit = netstat -ano | Select-String -SimpleMatch -Pattern $needle -ErrorAction SilentlyContinue |
               Where-Object { $_.Line.Contains('LISTENING') } | Select-Object -First 1
        if ($hit) {
            $parts = @(($hit.Line -split ' ') | Where-Object { $_ -ne '' })
            if ($parts.Count -ge 5) { return [int]$parts[$parts.Count - 1] }
        }
    } catch { }
    return 0
}

Write-Host ''
Write-Host 'TRPG 客户端 —— 停止本地静态服务器' -ForegroundColor Cyan
Write-Host '============================================'

# ---- 1. 定位端口 ----------------------------------------------------------
$target = $Port
if ($target -le 0 -and (Test-Path $PortFile)) {
    $raw = (Get-Content $PortFile -Raw -ErrorAction SilentlyContinue)
    if ($raw) { $target = [int]$raw.Trim() }
}

# ---- 2. 定位 PID（先信自己记录的 pid）------------------------------------
$targetPid = 0
if (Test-Path $JsonFile) {
    try {
        $j = Get-Content $JsonFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $cand = [int]$j.pid
        if ([int]$j.port -gt 0 -and $target -le 0) { $target = [int]$j.port }
        if (Test-IsOurServe $cand) { $targetPid = $cand }
    } catch { }
}

if ($targetPid -le 0 -and $target -gt 0) {
    $byPort = Get-PortOwnerPid $target
    if ($byPort -gt 0) { $targetPid = $byPort }
}

if ($targetPid -le 0 -and $target -le 0) {
    Write-Warn2 '未找到运行中的客户端（缺少 run/client.port 与 run/client.json）。'
    exit $EXIT_OK
}

# ---- 3. 停止 --------------------------------------------------------------
if ($targetPid -le 0) {
    Write-Warn2 ('端口 ' + $target + ' 上没有找到监听进程（可能已停止）。')
    if (Test-Path $PortFile) { Remove-Item $PortFile -Force; Write-Ok '已清理 run/client.port' }
    if (Test-Path $JsonFile) { Remove-Item $JsonFile -Force; Write-Ok '已清理 run/client.json' }
    exit $EXIT_OK
}

Write-Step ('目标端口：' + $target)
Write-Step ('目标进程 PID：' + $targetPid)

try {
    $proc = Get-Process -Id $targetPid -ErrorAction Stop
    Write-Step ('正在停止 ' + $proc.ProcessName + ' (PID ' + $targetPid + ') ...')
    Stop-Process -Id $targetPid -Force -ErrorAction Stop
} catch {
    Write-Fail ('停止进程失败：' + $_.Exception.Message)
    exit $EXIT_ENV
}

# ---- 4. 确认端口释放 ------------------------------------------------------
$freed = $false
if ($target -gt 0) {
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-PortFree $target) { $freed = $true; break }
        Start-Sleep -Milliseconds 200
    }
} else {
    $freed = $true
}

if ($freed) {
    Write-Ok ('端口 ' + $target + ' 已释放。')
} else {
    Write-Fail ('端口 ' + $target + ' 仍被占用（可能有残留进程）。')
}

# ---- 5. 清理发现文件（保留日志）------------------------------------------
if (Test-Path $PortFile) { Remove-Item $PortFile -Force; Write-Ok '已删除 run/client.port' }
if (Test-Path $JsonFile) { Remove-Item $JsonFile -Force; Write-Ok '已删除 run/client.json' }

if (-not $freed) {
    Write-Host ''
    exit $EXIT_ENV
}

Write-Host ''
Write-Host '  客户端已停止。' -ForegroundColor Green
Write-Host ''
exit $EXIT_OK

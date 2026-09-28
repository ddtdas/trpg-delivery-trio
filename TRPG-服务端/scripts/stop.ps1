<#
.SYNOPSIS
  TRPG 服务端（主持端）停止。
.DESCRIPTION
  由仓库根目录的 stop.bat 调用（bat 纯 ASCII；本脚本 UTF-8 带 BOM）。

  用法:
    stop.bat            读 run\server.port 定位端口；不存在则回退探测 9210..9230
    stop.bat 9300       显式指定要停止的端口

  流程: 定位端口 -> 取监听 PID -> 优雅停止 -> 等端口释放(<=10s) -> 必要时强杀
        -> 确认端口已释放 -> 删除 run\server.port 与 run\server.json（保留日志）
  退出码: 0 = 已停止 或 本就没有在运行
#>
param([string]$Port = '')

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$root = Split-Path -Parent $PSScriptRoot
$portMin = 9210
$portMax = 9230

$rundir   = Join-Path $root 'run'
$portfile = Join-Path $rundir 'server.port'
$jsonfile = Join-Path $rundir 'server.json'
$pidfile  = Join-Path $rundir 'server.pid'

function Test-PortInUse([int]$p) {
  # 三判据，任一命中即视为「被占用」。
  # ⚠️ 权威判据是 netstat，**不是**绑定探测：Windows 的 SO_REUSEADDR 允许在已有监听者
  #    之上再绑定，实测在 0.0.0.0:<p> 被真监听者占用时 TcpListener(127.0.0.1,<p>).Start()
  #    仍会成功（60/60），所以「绑定成功」不等于「端口空闲」。
  # 判据 1：Get-NetTCPConnection（快，但本机实测会漏报活着的监听者）
  try {
    $c = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
    if ($c) { return $true }
  } catch { }
  # 判据 2：netstat -ano（权威；且能覆盖绑定在非回环地址上的监听者）
  try {
    $hit = netstat -ano | Select-String -SimpleMatch -Pattern (':' + $p + ' ') -ErrorAction SilentlyContinue |
           Where-Object { $_.Line -match 'LISTENING' } | Select-Object -First 1
    if ($hit) { return $true }
  } catch { }
  # 判据 3：TcpListener 试绑（仅作最后兜底，不可单独作为「空闲」的证据）
  try {
    $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $p)
    $l.Start(); $l.Stop(); return $false
  } catch { return $true }
}

function Get-Health([int]$p) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri ('http://127.0.0.1:' + $p + '/api/health') -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -ne 200) { return $null }
    $j = $null
    try { $j = $r.Content | ConvertFrom-Json } catch { return $null }
    if ($j -and ($j.status -eq 'ok')) { return $j }
    return $null
  } catch { return $null }
}

# ------------------------------------------------ 身份判定（SPEC-SERVER-IDENTITY v1.0）
# SPEC §三 3)：Test-IsServerProc（命令行校验）**保留**作为防误杀；另在「是否本部署」的
# 判定上**优先使用** /__trpg_server__ 的 install_dir/deployment_id。
# 端点不可达 -> 退回既有命令行校验（**不得**因此放宽守卫）。

function Normalize-Path([string]$p) {
  # 路径规范化：统一分隔符、去尾分隔符、小写（Windows 路径大小写不敏感）。
  # 不调用 GetFullPath —— 目标路径可能指向别的部署（甚至不存在的目录），也必须能比较。
  if (-not $p) { return '' }
  $s = $p.Trim() -replace '/', '\'
  while ($s.Length -gt 3 -and $s.EndsWith('\')) { $s = $s.Substring(0, $s.Length - 1) }
  return $s.ToLowerInvariant()
}

function Get-PathDigest([string]$p) {
  # 与 app/web/identity.py 的 path_digest() 同算法：正斜杠归一 + 小写 + 去尾分隔符 -> SHA256 前 16 位。
  $s = (Normalize-Path $p).Replace('\', '/')
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $hash = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($s))
    $hex = (($hash | ForEach-Object { $_.ToString('x2') }) -join '')
    return $hex.Substring(0, 16)
  } finally { $sha.Dispose() }
}

function Get-OwnDeploymentId {
  # 本部署的稳定身份：首选 run\deployment.id（UUID v4，首次生成后每次启动复用），
  # 与服务端 app/web/identity.py 的 ensure_deployment_id() 同源同文件。
  $f = Join-Path $root 'run\deployment.id'
  try {
    if (Test-Path $f) {
      $raw = (Get-Content -Path $f -ErrorAction SilentlyContinue | Select-Object -First 1)
      $v = ("$raw").Trim()
      if ($v) { return $v }
    }
    $dir = Split-Path -Parent $f
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $v = ([guid]::NewGuid()).ToString()
    # 显式不带 BOM，方便 Python / 其它语言直接读取
    [System.IO.File]::WriteAllText($f, $v, (New-Object System.Text.UTF8Encoding($false)))
    return $v
  } catch {
    return (Get-PathDigest $root)
  }
}

function Get-ResponseTextUtf8($r) {
  # F1 修复：显式按 UTF-8 解码响应体，**不依赖服务端 Content-Type 里的 charset**。
  # Windows PowerShell 5.1 的 Invoke-WebRequest 在 Content-Type 无 charset 时按
  # ISO-8859-1 解码（HTTP/1.1 历史默认），会把 install_dir 里的非 ASCII（中文）路径
  # 解成乱码，使「install_dir 相等」这条直接判据恒为 False —— 并集退化为仅
  # deployment_id 一支，一旦 run\deployment.id 丢失/竞态，本部署会被误判为「别的部署」。
  # 服务端始终以 UTF-8 输出 JSON（app/web/identity.py），故这里直接按 UTF-8 解码原始字节。
  try {
    if ($r -and $r.RawContentStream) {
      $t = [System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
      if ($t) { return $t.TrimStart(@([char]0xFEFF)) }
    }
  } catch { }
  # 兜底：取不到原始字节流时退回 .Content（改造前行为）
  return [string]$r.Content
}

function Get-ServerIdentity([int]$p) {
  # SPEC §三 1)：GET /__trpg_server__。只有 service == 'trpg-server' 才算身份响应；
  # 旧版服务端（无该端点）/ 非 TRPG 进程 / 网络故障 -> 一律返回 $null。
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri ('http://127.0.0.1:' + $p + '/__trpg_server__') -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -ne 200) { return $null }
    $j = $null
    try { $j = (Get-ResponseTextUtf8 $r) | ConvertFrom-Json } catch { return $null }
    if ($j -and ($j.service -eq 'trpg-server')) { return $j }
    return $null
  } catch { return $null }
}

function Test-IsOwnDeployment($ident) {
  # install_dir 等于本部署根（规范化 + 大小写不敏感）—— 或 deployment_id 等于本部署 id。
  if (-not $ident) { return $false }
  $theirDir = Normalize-Path ([string]$ident.install_dir)
  if ($theirDir -and ($theirDir -eq (Normalize-Path $root))) { return $true }
  $theirId = ([string]$ident.deployment_id).Trim()
  if ($theirId) {
    $ownId = Get-OwnDeploymentId
    if ($ownId -and ($theirId -eq $ownId)) { return $true }
  }
  return $false
}

function Test-MayStopProc([int]$procId, [bool]$identReachable, [bool]$identIsOwn) {
  # 返回拒绝理由字符串；'' = 允许停止。
  #   ① 命令行校验（既有防误杀，**保留**，不得放宽）—— 与端点是否可达无关，永远先判；
  #   ② SPEC §三 3)：端点**可达**时，用 install_dir/deployment_id 判定「是否本部署」，
  #      不是本部署 -> 拒绝停止（避免误停别的部署）；
  #      端点**不可达** -> 退回 ① 的既有判据（不放宽、也不收紧）。
  if (-not (Test-IsServerProc $procId)) { return 'not-our-service' }
  if ($identReachable -and (-not $identIsOwn)) { return 'other-deployment' }
  return ''
}

function Test-PortConnectable([int]$p) {
  # 独立判据 A：能建立 TCP 连接 = 确有监听者。
  # 注意这是「连接」而不是「绑定」—— 不受 Windows SO_REUSEADDR 试绑陷阱影响
  # （0.0.0.0:<p> 被占时裸 bind 127.0.0.1:<p> 会成功，但 connect 一定能连上）。
  $c = $null
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect('127.0.0.1', $p, $null, $null)
    if (-not $iar.AsyncWaitHandle.WaitOne(800, $false)) { return $false }
    $c.EndConnect($iar)
    return $true
  } catch {
    return $false          # 连接被拒 = 无监听者
  } finally {
    if ($c) { try { $c.Close() } catch { } }
  }
}

function Test-NetstatListening([int]$p) {
  # 独立判据 B：netstat -ano 交叉校验（不经过 Get-NetTCPConnection）
  try {
    $hit = netstat -ano | Select-String -SimpleMatch -Pattern (':' + $p + ' ') -ErrorAction SilentlyContinue |
           Where-Object { $_.Line -match 'LISTENING' } | Select-Object -First 1
    if ($hit) { return $true }
  } catch { }
  return $false
}

function Test-PortStillBusy([int]$p) {
  # 「端口是否仍被占用」——用于守卫与释放确认，必须是**独立判据**：
  # 不得只依赖 Test-PortInUse，因为后者与查 PID 复用同一批探测源，两源同时失效会一起失灵。
  # 这里取并集，任一命中即视为「仍被占用」（只会更保守，不会漏判）：
  #   A) 真实 TCP 连接探测   B) netstat -ano   C) Test-PortInUse（三判据）
  if (Test-PortConnectable $p) { return $true }
  if (Test-NetstatListening $p) { return $true }
  if (Test-PortInUse $p) { return $true }
  return $false
}

function Test-PidListensOn([int]$procId, [int]$p) {
  # 该 PID 是否**真的**是端口 p 的监听者（netstat / CIM 交叉校验，任一确认即可）
  if ($procId -le 0) { return $false }
  try {
    $needle = ':' + $p + ' '
    $hits = netstat -ano | Select-String -SimpleMatch -Pattern $needle -ErrorAction SilentlyContinue |
            Where-Object { $_.Line -match 'LISTENING' }
    foreach ($h in @($hits)) {
      $parts = @(($h.Line -split ' ') | Where-Object { $_ -ne '' })
      if ($parts.Count -ge 5) {
        $v = 0
        if ([int]::TryParse($parts[$parts.Count - 1], [ref]$v) -and $v -eq $procId) { return $true }
      }
    }
  } catch { }
  try {
    $cim = @(Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue |
             Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($v in @($cim)) { if ([int]$v -eq $procId) { return $true } }
  } catch { }
  return $false
}

function Get-ListenPids([int]$p) {
  # Get-NetTCPConnection 本机实测会漏报活着的监听者，必须回退 netstat -ano。
  $list = @()
  try {
    $list = @(Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue |
              Select-Object -ExpandProperty OwningProcess -Unique)
  } catch { $list = @() }
  $list = @($list | Where-Object { $_ -and [int]$_ -gt 0 })
  if ($list.Count -gt 0) { return @($list | Select-Object -Unique) }

  try {
    $needle = ':' + $p + ' '
    $hits = netstat -ano | Select-String -SimpleMatch -Pattern $needle -ErrorAction SilentlyContinue |
            Where-Object { $_.Line.Contains('LISTENING') }
    foreach ($h in @($hits)) {
      $parts = @(($h.Line -split ' ') | Where-Object { $_ -ne '' })
      if ($parts.Count -ge 5) {
        $cand = 0
        if ([int]::TryParse($parts[$parts.Count - 1], [ref]$cand) -and $cand -gt 0) { $list += $cand }
      }
    }
  } catch { }
  return @($list | Select-Object -Unique)
}

function Test-IsServerProc([int]$procId) {
  # 校验该 PID 确实是本服务端（避免 PID 被回收后误杀无关进程）。
  if ($procId -le 0) { return $false }
  try {
    $proc = Get-CimInstance Win32_Process -Filter ("ProcessId=$procId") -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    $cl = [string]$proc.CommandLine
    if ($cl -like '*_serve.py*' -or $cl -like '*trpg-server*') { return $true }
    return $false
  } catch { return $false }
}

function Get-DiscoveryPid([int]$p) {
  # 优先 run\server.json 的 pid，其次 run\server.pid。
  # 采用前必须**三重校验**：① 进程存在 ② 命令行确为本服务 ③ **确在监听目标端口**。
  # 任一不满足 -> 不采用该 PID —— 既避免 PID 复用误杀无关进程，
  # 也避免「拿到一个非空 PID 就绕过 Count -eq 0 守卫」而报假成功。
  $cand = 0
  if (Test-Path $jsonfile) {
    try {
      $j = (Get-Content $jsonfile -Raw -ErrorAction SilentlyContinue) | ConvertFrom-Json
      if ($j -and $j.pid) { $cand = [int]$j.pid }
    } catch { $cand = 0 }
  }
  if ($cand -le 0 -and (Test-Path $pidfile)) {
    $raw = (Get-Content $pidfile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $tmp = 0
    if ([int]::TryParse(("$raw").Trim(), [ref]$tmp) -and $tmp -gt 0) { $cand = $tmp }
  }
  if ($cand -le 0) { return 0 }
  if (-not (Test-IsServerProc $cand)) { return 0 }      # ② 命令行必须是本服务端
  # ③ 必须真在监听目标端口（队长要求）。要求该 PID **出现在 Get-ListenPids $p 的结果里**；
  #    不满足则返回 0，让它落到守卫报错 —— 不得因「PID 非空」而绕过 Count -eq 0 守卫，
  #    否则陈旧/复用的服务端 PID 会去停一个与本端口无关的实例。
  #    取并集：字面量成员判定 ∪ netstat/CIM 直查（Test-PidListensOn），
  #    两路任一确认即通过 —— 保证不会因单一探测源抖动把合法 PID 判死（不比原来更严）。
  $listeners = @(Get-ListenPids $p)
  if ($listeners -contains $cand) { return $cand }
  if (Test-PidListensOn $cand $p) { return $cand }
  return 0
}

Write-Host '============================================================'
Write-Host '   TRPG 服务端（主持端）停止'
Write-Host '============================================================'

# ---------------------------------------------------------------- 1) 定位端口
$target = 0
$source = ''

if ($Port -ne '') {
  $tmp = 0
  if (-not [int]::TryParse(("$Port").Trim(), [ref]$tmp) -or $tmp -lt 1 -or $tmp -gt 65535) {
    Write-Host ('[错误] 端口参数无效: "' + $Port + '"')
    exit 1
  }
  $target = $tmp
  $source = '命令行参数'
}
elseif (Test-Path $portfile) {
  $raw = (Get-Content $portfile -ErrorAction SilentlyContinue | Select-Object -First 1)
  $tmp = 0
  if ([int]::TryParse(("$raw").Trim(), [ref]$tmp) -and $tmp -gt 0) {
    $target = $tmp
    $source = 'run\server.port'
  }
}

if ($target -eq 0) {
  # 回退 1：优先找**本部署**的实例（SPEC §三 3)：身份判据优先用 /__trpg_server__）。
  for ($p = $portMin; $p -le $portMax; $p++) {
    if (Test-IsOwnDeployment (Get-ServerIdentity $p)) { $target = $p; $source = '回退探测 /__trpg_server__（本部署）'; break }
  }
}
if ($target -eq 0) {
  # 回退 2（既有行为，保留）：区间内是否有正在服务的实例。
  # 若命中的是别的部署，后面的「是否本部署」守卫会拒绝停止它（不放宽守卫）。
  for ($p = $portMin; $p -le $portMax; $p++) {
    if (Get-Health $p) { $target = $p; $source = '回退探测 /api/health'; break }
  }
}

if ($target -eq 0) {
  Write-Host ('未发现运行中的 TRPG 服务端（' + $portMin + '..' + $portMax + ' 无健康实例，且无 run\server.port）。')
  # 清理可能残留的陈旧发现文件
  Remove-Item $portfile -Force -ErrorAction SilentlyContinue
  Remove-Item $jsonfile -Force -ErrorAction SilentlyContinue
  Write-Host '端口空闲，无需停止。'
  exit 0
}

Write-Host ('   端口 : ' + $target + '  (来源: ' + $source + ')')

# SPEC §三 3)：优先用身份端点判定「是否本部署」。端点不可达 -> identReachable=$false
# -> 守卫退回既有命令行校验（既不放宽、也不收紧）。
$ident = Get-ServerIdentity $target
$identReachable = ($null -ne $ident)
$identIsOwn = $false
if ($identReachable) { $identIsOwn = Test-IsOwnDeployment $ident }
if ($identReachable) {
  if ($identIsOwn) {
    Write-Host ('   身份 : 是本部署（install_dir=' + [string]$ident.install_dir + '，pid=' + [string]$ident.pid + '）')
  } else {
    Write-Host ('   身份 : 不是本部署（install_dir=' + [string]$ident.install_dir + '，deployment_id=' + [string]$ident.deployment_id + '）')
  }
} else {
  Write-Host '   身份 : 无身份端点 /__trpg_server__（旧版服务端或非本服务）—— 退回命令行校验'
}

# ---------------------------------------------------------------- 2) 取 PID
# ② 按端口反查（Get-NetTCPConnection -> netstat -ano 回退，见 Get-ListenPids）
$pids = Get-ListenPids $target
if ($pids.Count -eq 0) {
  # ① 退化为用发现文件记录的 PID，但必须先校验命令行确为服务端
  $dp = Get-DiscoveryPid $target
  if ($dp -gt 0) {
    $pids = @($dp)
    Write-Host ('   回退 : 使用发现文件记录的 PID ' + $dp + '（已校验：进程存在 + 命令行为本服务端 + 确在监听该端口）')
  } else {
    Write-Host '   提示 : 发现文件中的 PID 缺失/已失效/命令行不匹配，未采用（防止误杀无关进程）。'
  }
}

if ($pids.Count -eq 0) {
  # 关键守卫：找不到 PID != 端口空闲。Get-NetTCPConnection 会漏报活监听者，
  # 若此处直接删发现文件并 exit 0，就会「报成功但服务端仍在跑」（孤儿进程缺陷）。
  # 判据必须是**不依赖端口枚举**的信号，否则两源同时失效时会一起失灵。
  #   Test-PortStillBusy = 真实 TCP connect ∪ netstat ∪ Test-PortInUse（三判据）
  # 其中真实 TCP connect 与端口枚举完全无关，是「端口仍被占」的独立证据。
  # 注：不再叠加 HTTP /api/health 探测 —— 它与 connect 同 host，HTTP 200 必然蕴含
  #     TCP 可连，属真子集（不增加覆盖，只在空闲路径上多一次 HTTP 探测）。
  if (Test-PortStillBusy $target) {
    Write-Host ('[错误] 端口 ' + $target + ' 仍被占用，但无法确定监听进程 PID。')
    Write-Host '        已保留 run\server.port / run\server.json，未做任何清理。'
    Write-Host ('        请手动检查: Get-NetTCPConnection -State Listen -LocalPort ' + $target)
    Write-Host ('                    netstat -ano ^| findstr :' + $target)
    exit 1
  }
  Write-Host ('[提示] 端口 ' + $target + ' 当前无监听进程（可能已停止）。')
  Remove-Item $portfile -Force -ErrorAction SilentlyContinue
  Remove-Item $jsonfile -Force -ErrorAction SilentlyContinue
  Remove-Item $pidfile -Force -ErrorAction SilentlyContinue
  Write-Host '端口空闲，无需停止。'
  exit 0
}

# ---------------------------------------------------------------- 3) 优雅停止
$stoppedAny = $false
$refusedOtherDeployment = $false

foreach ($procId in $pids) {
  $reason = Test-MayStopProc $procId $identReachable $identIsOwn
  if ($reason -eq 'not-our-service') {
    Write-Host ('   跳过 : PID ' + $procId + ' 的命令行不是本服务端，拒绝误杀（PID 复用防护）。')
    continue
  }
  if ($reason -eq 'other-deployment') {
    $refusedOtherDeployment = $true
    Write-Host ('   跳过 : PID ' + $procId + ' 上的 TRPG 服务端不是本部署（install_dir=' + [string]$ident.install_dir + '），拒绝停止别的部署。')
    continue
  }
  try {
    Stop-Process -Id ([int]$procId) -ErrorAction Stop
    $stoppedAny = $true
    Write-Host ('   已发送停止信号 PID ' + $procId)
  } catch {
    Write-Host ('   警告: PID ' + $procId + ' 无法停止或已退出（' + $_.Exception.Message + '）')
  }
}

$released = $false
for ($i = 0; $i -lt 10; $i++) {
  if (-not (Test-PortStillBusy $target)) { $released = $true; break }
  Start-Sleep -Seconds 1
}

# ---------------------------------------------------------------- 4) 必要时强杀
if (-not $released) {
  Write-Host '   优雅停止超时，改用强制结束 ...'
  $left = Get-ListenPids $target
  foreach ($procId in $left) {
    $reason = Test-MayStopProc $procId $identReachable $identIsOwn
    if ($reason -eq 'not-our-service') {
      Write-Host ('   跳过 : PID ' + $procId + ' 的命令行不是本服务端，拒绝误杀（PID 复用防护）。')
      continue
    }
    if ($reason -eq 'other-deployment') {
      $refusedOtherDeployment = $true
      Write-Host ('   跳过 : PID ' + $procId + ' 上的 TRPG 服务端不是本部署（install_dir=' + [string]$ident.install_dir + '），拒绝停止别的部署。')
      continue
    }
    try {
      Stop-Process -Id ([int]$procId) -Force -ErrorAction Stop
      $stoppedAny = $true
      Write-Host ('   已强制结束 PID ' + $procId)
    } catch { }
  }
  for ($i = 0; $i -lt 5; $i++) {
    if (-not (Test-PortStillBusy $target)) { $released = $true; break }
    Start-Sleep -Seconds 1
  }
}

# ---------------------------------------------------------------- 5) 确认 + 清理
if (-not $released) {
  if ($refusedOtherDeployment -and (-not $stoppedAny)) {
    # SPEC §三 3)：不是本部署 -> 拒绝停止（不误停别的部署），如实报错，不报假成功。
    Write-Host ('[错误] 端口 ' + $target + ' 上的 TRPG 服务端不是本部署，已拒绝停止（不误停别的部署）。')
    Write-Host ('        占用者 install_dir: ' + [string]$ident.install_dir)
    Write-Host ('        占用者 deployment_id: ' + [string]$ident.deployment_id)
    Write-Host '        已保留 run\server.port / run\server.json，未做任何清理。'
    exit 1
  }
  Write-Host ('[错误] 端口 ' + $target + ' 仍被占用，未能释放（不报假成功）。')
  Write-Host '        已保留 run\server.port / run\server.json，未做任何清理。'
  Write-Host ('        请手动检查: Get-NetTCPConnection -State Listen -LocalPort ' + $target)
  Write-Host ('                    netstat -ano ^| findstr :' + $target)
  exit 1
}

Write-Host ('   端口 ' + $target + ' 已释放')
Remove-Item $portfile -Force -ErrorAction SilentlyContinue
Remove-Item $jsonfile -Force -ErrorAction SilentlyContinue
Remove-Item $pidfile  -Force -ErrorAction SilentlyContinue
Write-Host '   已删除 run\server.port 与 run\server.json（日志保留）'
Write-Host '停止完成。'
exit 0

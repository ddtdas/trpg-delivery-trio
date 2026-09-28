<#
.SYNOPSIS
    TRPG 客户端 —— 启动本地静态服务器并打开玩家端页面。

.DESCRIPTION
    端口分支（与 SPEC §二 服务端裁决一致）：
      · 端口空闲                    -> 正常启动
      · 端口被占 且是本客户端        -> 幂等：打印现有地址，exit 0，不起第二实例
      · 端口被占 且是别的进程        -> 真冲突：打印占用者 PID，exit 2（不静默换端口）
    显式指定端口同样走这三条分支；自适应扫描时先查区间内是否已有本客户端。

    身份判定用 GET /__trpg_client__（对应服务端的 /api/health），
    不依赖 run/client.json —— 该文件可能被删或过期。

    启动成功后落盘 run/client.port 与 run/client.json。
    自动发现服务端：未显式给出 -ServerUrl 时读取 ../trpg-server/run/server.json。

    退出码：0 成功（或已在运行）| 1 环境/依赖错误 | 2 端口冲突 | 3 启动超时

.PARAMETER Port
    指定端口。按上面的分支表处理。

.PARAMETER ServerUrl
    服务端地址，如 http://192.168.10.110:9210。省略则自动发现。
.PARAMETER BindHost
    Listen address. Default 0.0.0.0 (LAN reachable so players on the network can open the page).
    Pass 0.0.0.0 to expose on the LAN (explicit opt-in only).
    Env var TRPG_CLIENT_HOST also overrides the serve.py default.

#>
[CmdletBinding()]
param(
    [int]$Port = 0,
    [string]$ServerUrl = '',
    [string]$BindHost = '0.0.0.0'
)

$ErrorActionPreference = 'Stop'

$EXIT_OK      = 0
$EXIT_ENV     = 1
$EXIT_PORT    = 2
$EXIT_TIMEOUT = 3

$ScriptDir = $PSScriptRoot
$RepoRoot  = Split-Path -Parent $ScriptDir
$RunDir    = Join-Path $RepoRoot 'run'
$PortFile  = Join-Path $RunDir 'client.port'
$JsonFile  = Join-Path $RunDir 'client.json'
$LogFile   = Join-Path $RunDir 'client.log'
$ServePy   = Join-Path $ScriptDir 'serve.py'
$ClientDir = Join-Path $RepoRoot 'client'
$IndexHtml = Join-Path $ClientDir 'index.html'

# 同机服务端发现文件：<同级目录>/<服务端目录名>/run/server.json
# 候选目录名：开发树里叫 trpg-server；交付包解压后叫「TRPG-服务端」（中文目录名）。
$SiblingRoot = Split-Path -Parent $RepoRoot
$ServerJson  = ''
foreach ($sibName in @('trpg-server', 'TRPG-服务端')) {
    $sibCand = Join-Path (Join-Path (Join-Path $SiblingRoot $sibName) 'run') 'server.json'
    if (Test-Path $sibCand) { $ServerJson = $sibCand; break }
}
if (-not $ServerJson) {
    $ServerJson = Join-Path (Join-Path (Join-Path $SiblingRoot 'trpg-server') 'run') 'server.json'
}

$PortLow  = 8080
$PortHigh = 8090
$WaitSec  = 30
$IdentityPath = '/__trpg_client__'

# 无人值守/自动化测试：设置 TRPG_NO_BROWSER=1 可跳过自动打开浏览器
$NoBrowser = ($env:TRPG_NO_BROWSER -eq '1')

function Write-Step([string]$msg) { Write-Host ('  ' + $msg) }
function Write-Ok([string]$msg)   { Write-Host ('  [OK]   ' + $msg) -ForegroundColor Green }
function Write-Warn2([string]$msg){ Write-Host ('  [WARN] ' + $msg) -ForegroundColor Yellow }
function Write-Fail([string]$msg) { Write-Host ('  [FAIL] ' + $msg) -ForegroundColor Red }

function Get-PythonExe {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

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

function Get-PortOwnerPid([int]$p) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction Stop |
                Select-Object -First 1
        if ($conn) { return [int]$conn.OwningProcess }
    } catch { }
    return 0
}

# 某端口上的监听者是不是本客户端？(对应服务端的 /api/health 探针)
function Test-ClientIdentity([int]$p) {
    try {
        $uri = 'http://127.0.0.1:' + $p + $IdentityPath
        $resp = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200 -and $resp.Content.Contains('trpg-client')) {
            return $true
        }
    } catch { }
    return $false
}

function Get-CurrentSessionId {
    # 本进程所在 Windows 会话号。0 = 服务/非交互（无桌面），>0 = 交互式桌面。
    try { return [int](Get-Process -Id $PID).SessionId } catch { }
    try { return [int][System.Diagnostics.Process]::GetCurrentProcess().SessionId } catch { }
    return -1
}

function Get-InteractiveSessionId {
    # explorer.exe 只跑在交互式桌面会话里 —— 用它判定"用户桌面"在哪个会话。
    try {
        $ex = @(Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" -ErrorAction Stop |
                Where-Object { $_.SessionId -gt 0 } | Sort-Object SessionId)
        if ($ex.Count -gt 0) { return [int]$ex[0].SessionId }
    } catch { }
    return -1
}

function Start-UiCrossSession([string]$url) {
    # 跨会话把 UI 投到用户桌面：当前进程在 Session 0（无桌面）时，
    # 直接 Start-Process 只会在 Session 0 里开一个用户**看不见**的窗口。
    # 这里用计划任务 /IT（Interactive only）把窗口投到已登录的交互式会话。
    # 注意：schtasks /TR 对嵌套引号很脆弱，故先落一个临时 .cmd 包装器。
    $chrome = Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'
    if (-not (Test-Path -LiteralPath $chrome)) {
        $chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    }
    if (-not (Test-Path -LiteralPath $chrome)) {
        $chrome = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    }
    if (-not (Test-Path -LiteralPath $chrome)) {
        Write-Warn2 '  [跨会话] 未找到 Chrome/Edge 可执行文件，无法跨会话打开。'
        return $false
    }
    $tag    = [guid]::NewGuid().ToString('N').Substring(0,8)
    $tmpCmd = Join-Path $env:TEMP ('trpg_openui_' + $tag + '.cmd')
    $tn     = 'TRPG_OpenUI_' + $tag
    $body = @(
        '@echo off',
        ('start "" "' + $chrome + '" --app=' + $url + ' --new-window --no-first-run --no-default-browser-check')
    )
    try {
        [IO.File]::WriteAllLines($tmpCmd, $body, (New-Object System.Text.ASCIIEncoding))
    } catch {
        Write-Warn2 ('  [跨会话] 写临时包装脚本失败：' + $_.Exception.Message)
        return $false
    }
    # /ST 必须给一个『未来』时间：否则 schtasks 会往 stderr 写 WARNING，
    # 而 native 的 stderr 在 $ErrorActionPreference='Stop' 下会被当成终止性错误
    # 直接抛进 catch，导致『任务其实建好了』却被误判为失败（本机曾实测到）。
    # 同时本地临时用 Continue，并用『任务是否存在』而非 $LASTEXITCODE 判定。
    $oldEa = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $stTime = (Get-Date).AddMinutes(2).ToString('HH:mm')
        $r1 = schtasks /Create /TN $tn /TR $tmpCmd /SC ONCE /ST $stTime /F /IT /RL LIMITED 2>&1 | Out-String
        $null = schtasks /Query /TN $tn 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 ('  [跨会话] 创建计划任务失败：' + ($r1 -replace '\s+', ' ').Trim())
            return $false
        }
        $r2 = schtasks /Run /TN $tn 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 ('  [跨会话] 运行计划任务失败：' + ($r2 -replace '\s+', ' ').Trim())
            return $false
        }
        Start-Sleep -Seconds 3
        return $true
    } catch {
        Write-Warn2 ('  [跨会话] 计划任务方式异常：' + $_.Exception.Message)
        return $false
    } finally {
        $ErrorActionPreference = $oldEa
        try { $null = schtasks /Delete /TN $tn /F 2>&1 } catch { }
        try { Remove-Item -LiteralPath $tmpCmd -Force -ErrorAction SilentlyContinue } catch { }
    }

}

function Invoke-OpenUi([int]$p, [string]$srvUrl) {
    # 统一的开 UI 入口：正常启动 与 幂等（已在运行）两条路径都必须经过这里。
    # 修复点 1：此前开浏览器代码只在「正常启动」的末尾，而幂等分支提前 exit 0。
    # 修复点 2：Session 0（SSH/服务方式启动）下直接 Start-Process，窗口开在无桌面的会话里，
    #           用户在自己的桌面上看不见 —— 此时改用计划任务跨会话投递。
    if ($NoBrowser) {
        Write-Warn2 '已跳过自动打开浏览器（TRPG_NO_BROWSER=1）。'
        return
    }
    $url = Build-PageUrl $p $srvUrl

    $mySess = Get-CurrentSessionId
    $uiSess = Get-InteractiveSessionId

    if ($mySess -ne 0 -or $uiSess -le 0) {
        # 已是交互式会话（用户双击 start.bat 的常见路径）-> 保持原有逻辑不变。
        # 或系统没有交互式会话 -> 也没有可投递的桌面，走原逻辑即可。
        if ($mySess -eq 0 -and $uiSess -le 0) {
            Write-Warn2 '当前为非交互会话且未检测到已登录桌面，浏览器可能不可见。'
        } else {
            Write-Step ('当前为交互式会话（Session ' + $mySess + '），直接打开 UI。')
        }
        Start-UiInSession $url
        return
    }

    # 当前在 Session 0，且有交互式桌面 -> 跨会话投递
    Write-Step ('当前为非交互会话（Session 0），检测到交互式桌面在 Session ' + $uiSess + '，改用计划任务跨会话打开 UI ...')
    if (Start-UiCrossSession $url) {
        Write-Ok ('已通过计划任务在会话 ' + $uiSess + ' 打开 UI：' + $url)
    } else {
        Write-Warn2 '跨会话打开失败，请手工在桌面访问：' + $url
        Write-Warn2 '（这也是唯一能看到界面的方式：本进程运行在无桌面的 Session 0。）'
    }
}

function Start-UiInSession([string]$url) {
    # 同会话打开：复用 open_ui.ps1 的浏览器探测（不重复实现其逻辑）。
    $openUi = Join-Path $ScriptDir 'open_ui.ps1'
    if (-not (Test-Path $openUi)) {
        Write-Warn2 ('未找到 ' + $openUi + '，改用系统默认浏览器打开。')
        try {
            Start-Process $url | Out-Null
            Write-Ok ('已用系统默认浏览器打开：' + $url)
        } catch {
            Write-Warn2 ('无法自动打开浏览器：' + $_.Exception.Message)
            Write-Warn2 ('请手工访问：' + $url)
        }
        return
    }
    # 不再用 | Out-Null 吞掉 open_ui.ps1 的输出：它的 [UI] 提示与错误信息必须回显。
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $openUi -Url $url 2>&1 |
            ForEach-Object { Write-Host ('  ' + $_) }
        if ($LASTEXITCODE -eq 0) {
            Write-Ok '已打开浏览器。'
        } else {
            Write-Warn2 ('open_ui.ps1 退出码 ' + $LASTEXITCODE + '，浏览器可能未打开。')
            Write-Warn2 ('请手工访问：' + $url)
        }
    } catch {
        Write-Warn2 ('无法自动打开浏览器：' + $_.Exception.Message)
        Write-Warn2 ('请手工访问：' + $url)
    }
}

function Build-PageUrl([int]$p, [string]$srv) {
    $u = 'http://127.0.0.1:' + $p + '/index.html'
    if ($srv) { $u = $u + '?server=' + [System.Uri]::EscapeDataString($srv) }
    return $u
}

function Show-Info([int]$p, [string]$srv, [int]$procId) {
    # 打印的地址必须与真正打开的地址一致：方案 B 下页面一律同源，
    # 真实服务端只作为反代目标显示（否则用户看到的 URL 与实际打开的不符）。
    $u = Build-PageUrl $p ('http://127.0.0.1:' + $p)
    # R2 fix: print the ACTUAL bound address, not the intended one.
    # In the idempotent path $BindHost could differ from what the already-running
    # instance was really listening on, so the banner used to state something untrue.
    $actualBind = $BindHost
    try {
        $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn -and $conn.LocalAddress) { $actualBind = [string]$conn.LocalAddress }
    } catch { }
    Write-Host ('  bind: ' + $actualBind + ':' + $p)
    if ($actualBind -eq '0.0.0.0' -or $actualBind -eq '::') {
        $lanIps = @()
        try {
            $lanIps = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
                Where-Object { $_.AddressFamily -eq 'InterNetwork' -and -not $_.IPAddressToString.StartsWith('127.') } |
                ForEach-Object { $_.IPAddressToString }
        } catch { }
        foreach ($ip in $lanIps) { Write-Host ('  LAN url: http://' + $ip + ':' + $p + '/index.html') }
    }
    Write-Host ''
    Write-Host '--------------------------------------------'
    Write-Host ('  客户端地址：' + $u) -ForegroundColor Green
    Write-Host ('  本地端口：' + $p)
    Write-Host ('  服务端：' + $(if ($srv) { $srv } else { '（未自动发现：/api 与 /ws 将返回 502 提示）' }))
    Write-Host ('  反代  ：同源转发 /api/* /access/* /ws -> ' + $(if ($srv) { $srv } else { '<未解析>' }))
    if ($procId -gt 0) { Write-Host ('  进程 PID：' + $procId) }
    Write-Host ('  停止服务：stop.bat')
    Write-Host '--------------------------------------------'
    Write-Host ''
}

Write-Host ''
Write-Host 'TRPG 客户端 —— 启动本地静态服务器' -ForegroundColor Cyan
Write-Host '============================================'

# ---- 1. 环境检查 ----------------------------------------------------------
$py = Get-PythonExe
if (-not $py) {
    Write-Fail 'Python 未安装或不在 PATH 中。请安装 Python 3.12+ 后重试。'
    exit $EXIT_ENV
}
# 只取「含版本号的那一行」：某些 Python 发行版会在 -c 时向 stdout 多吐一行
# （发行版 banner / sitecustomize.py），那样 $verText 会变成数组，
# 直接 [version] 转换会抛未捕获异常，主入口 start.bat 会崩而不是给出中文提示。
$verRaw  = & $py -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
$verText = ''
if ($verRaw) {
    $vc = @($verRaw) | Where-Object { $_ -match '^\s*\d+\.\d+' } | Select-Object -Last 1
    if ($vc) { $verText = $vc.ToString().Trim() }
}
if ($LASTEXITCODE -ne 0 -or -not $verText) {
    Write-Fail 'Python 无法执行或版本号无法解析，请检查安装。'
    exit $EXIT_ENV
}
$ver = $null
try { $ver = [version]$verText } catch { $ver = $null }
if (-not $ver) {
    Write-Fail ('无法解析 Python 版本号（原始输出：' + $verText + '）。请确认 python 可正常执行。')
    exit $EXIT_ENV
}
if ($ver -lt [version]'3.12') {
    Write-Fail ('Python 版本过低：' + $ver + '（需要 3.12+）。')
    exit $EXIT_ENV
}
Write-Ok ('Python ' + $ver + '  ->  ' + $py)

if (-not (Test-Path $ServePy)) {
    Write-Fail ('缺少静态服务器脚本：' + $ServePy)
    exit $EXIT_ENV
}
if (-not (Test-Path $IndexHtml)) {
    Write-Fail ('缺少页面文件：' + $IndexHtml)
    exit $EXIT_ENV
}
if (-not (Test-Path $RunDir)) {
    New-Item -ItemType Directory -Path $RunDir -Force | Out-Null
}

# ---- 2. 解析服务端地址 ----------------------------------------------------
$resolved = $ServerUrl
if (-not $resolved) {
    if (Test-Path $ServerJson) {
        try {
            $sj = Get-Content $ServerJson -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([int]$sj.port -gt 0) {
                $resolved = 'http://127.0.0.1:' + [int]$sj.port
                Write-Ok ('自动发现服务端：' + $resolved)
            }
        } catch {
            Write-Warn2 '服务端发现文件无法解析。'
        }
    }
}
if (-not $resolved) {
    Write-Warn2 '未找到服务端地址，页面将提示手工填写。'
}

# ---- 3. 端口分支（SPEC §二 裁决分支表）-----------------------------------
$chosen = 0
$alreadyRunning = $false

if ($Port -gt 0) {
    if (Test-PortFree $Port) {
        $chosen = $Port
        Write-Ok ('使用指定端口 ' + $chosen)
    }
    elseif (Test-ClientIdentity $Port) {
        $alreadyRunning = $true
        $chosen = $Port
    }
    else {
        $owner = Get-PortOwnerPid $Port
        $ownerText = ''
        if ($owner -gt 0) { $ownerText = '（占用者 PID ' + $owner + '）' }
        Write-Fail ('指定端口 ' + $Port + ' 已被其它进程占用' + $ownerText + '，退出（不自动换端口）。')
        exit $EXIT_PORT
    }
}
else {
    foreach ($p in $PortLow..$PortHigh) {
        if ((-not (Test-PortFree $p)) -and (Test-ClientIdentity $p)) {
            $alreadyRunning = $true
            $chosen = $p
            break
        }
    }
    if (-not $alreadyRunning) {
        foreach ($p in $PortLow..$PortHigh) {
            if (Test-PortFree $p) { $chosen = $p; break }
        }
        if ($chosen -eq 0) {
            Write-Fail ('端口 ' + $PortLow + '-' + $PortHigh + ' 全部被占用，无法启动。')
            exit $EXIT_PORT
        }
        Write-Ok ('自适应端口：' + $chosen)
    }
}

# ---- 4. 幂等：本客户端已在运行 -------------------------------------------
if ($alreadyRunning) {
    Write-Ok ('端口 ' + $chosen + ' 上已有本客户端在运行（幂等，不重复启动）。')
    Set-Content -Path $PortFile -Value "$chosen" -Encoding ASCII -NoNewline
    try {
        $cj = Get-Content -Raw $JsonFile -Encoding UTF8 | ConvertFrom-Json
        if ($cj.host) {
            if (([string]$cj.host) -ne $BindHost) {
                Write-Warn2 ('运行中的实例监听 ' + $cj.host + '，与请求的 ' + $BindHost + ' 不一致；如需变更请先运行 stop.bat 再启动。')
            }
            $BindHost = [string]$cj.host
        }
    } catch { }
    Show-Info $chosen $resolved 0
    # 幂等分支同样要打开 UI：用户双击 start.bat 的意图就是「我要看到界面」。
    Invoke-OpenUi $chosen $resolved
    exit $EXIT_OK
}

# ---- 5. 启动静态服务器 ----------------------------------------------------
# 注意：不使用 -RedirectStandardOutput/-RedirectStandardError，
# 否则被拉起的 python 会继承本进程的 stdout 句柄，调用方（cmd/PowerShell）
# 会一直等不到管道 EOF 而卡住。日志由 serve.py 自己打开 --log 文件写入。
# SPEC §六 方案 B：页面一律走同源（页面 origin = 本机静态服务），
# 由 serve.py 把 /api/*、/access/*、/ws 反代到真实服务端。
# 这样 fetch 与 WebSocket 都不会被同源策略拦截（跨源会被拦）。
# t5 fix (tester INFO-W1 / t2 留档 W1)：优先用 WMI(Win32_Process.Create) 分离式启动
# —— 与 TRPG-服务端 scripts\start.ps1 同构。Start-Process 启动的子进程留在调用方
# 会话内，SSH/远程等**非交互**会话断开时会被回收；WMI 启动后进程挂在 WmiPrvSE 下，
# 跨会话存活。WMI 不可用（返回非 0 / 异常）时回退 Start-Process，交互式双击不受影响。
$pageServer = 'http://127.0.0.1:' + $chosen
$pageUrl = Build-PageUrl $chosen $pageServer

Write-Step '正在启动静态服务器 ...'
$launchArgs = @(
    $ServePy,
    '--port', "$chosen",
    '--host', "$BindHost",
    '--json', $JsonFile,
    '--root', $ClientDir,
    '--log',  $LogFile
)
if ($resolved) {
    $launchArgs += @('--proxy-target', $resolved)
}
$serverPid = 0
$proc = $null
$launched = $false
# WMI CommandLine 是单串：每段参数用双引号包裹（路径含中文/空格均安全）。
$quoted = @($launchArgs | ForEach-Object { '"' + $_ + '"' })
$cmdline = '"' + $py + '" ' + ($quoted -join ' ')
try {
    $res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -ErrorAction Stop -Arguments @{
             CommandLine      = $cmdline
             CurrentDirectory = $RepoRoot
           }
    if ($res -and ($res.ReturnValue -eq 0) -and ($res.ProcessId -gt 0)) {
        $serverPid = [int]$res.ProcessId
        $launched = $true
        Write-Ok ('分离式启动 PID ' + $serverPid)
    } else {
        Write-Warn2 ('分离式启动返回码 ' + $(if ($res) { $res.ReturnValue } else { 'null' }) + '，回退 Start-Process')
    }
} catch {
    Write-Warn2 ('分离式启动失败（' + $_.Exception.Message + '），回退 Start-Process')
}

if (-not $launched) {
    # 回退路径：功能可用；非交互调用方若用管道捕获输出，需等服务退出才会收到 EOF。
    $proc = Start-Process -FilePath $py -ArgumentList $launchArgs -WindowStyle Hidden -PassThru
    if ($proc) { $serverPid = $proc.Id }
}
if ($serverPid -le 0) {
    Write-Fail '无法创建静态服务器进程。'
    exit $EXIT_ENV
}

# ---- 6. 等待就绪（身份探针）----------------------------------------------
$deadline = (Get-Date).AddSeconds($WaitSec)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if (Test-ClientIdentity $chosen) { $ready = $true; break }
    Start-Sleep -Milliseconds 400
}
if (-not $ready) {
    Write-Fail ('静态服务器在 ' + $WaitSec + ' 秒内未就绪，已终止。')
    Write-Step ('日志：' + $LogFile)
    if ($serverPid -gt 0) { Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue }
    exit $EXIT_TIMEOUT
}
Write-Ok '静态服务器已就绪。'

# ---- 7. 落盘端口发现文件 --------------------------------------------------
Set-Content -Path $PortFile -Value "$chosen" -Encoding ASCII -NoNewline
Write-Ok ('已写入 ' + $PortFile)

# ---- 8. 打开浏览器 --------------------------------------------------------
Invoke-OpenUi $chosen $pageServer

Show-Info $chosen $resolved $serverPid
exit $EXIT_OK

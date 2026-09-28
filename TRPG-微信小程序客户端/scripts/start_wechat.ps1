<#
.SYNOPSIS
  TRPG 微信小程序客户端 —— 启动（导入微信开发者工具）。
.DESCRIPTION
  小程序无法像 Web 客户端那样由脚本直接"弹出界面"：它必须由「微信开发者工具」
  编译并载入模拟器。因此本脚本的职责是：
    1) 探测微信开发者工具的命令行入口 cli.bat；
    2) 找到就用 cli open --project <本目录> 自动导入并打开项目；
    3) 找不到就打印清晰的中文指引（下载地址 / 安装位置 / 手工导入步骤），
       并以非 0 退出码结束 —— 绝不做"必然失败的假启动"。
.NOTES
  cli.bat 需要先在开发者工具里开启「设置 → 安全设置 → 服务端口」，
  否则即使工具已安装也可能不存在 cli.bat。
  退出码：0 = 已成功调用 cli 打开项目；2 = 未找到开发者工具/ cli.bat；3 = cli 调用失败。
#>
[CmdletBinding()]
param(
    [switch]$Wait
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { <# 重定向输出时可能失败，属无害：编码只影响显示，不影响探测与启动 #> }

$EXIT_OK      = 0
$EXIT_NOCLI   = 2
$EXIT_FAILED  = 3

# scripts\start_wechat.ps1 -> 上一级即小程序工程根（含 app.json 的那一层）
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Write-Head([string]$m) { Write-Host $m -ForegroundColor Cyan }
function Write-Ok([string]$m)   { Write-Host ('  [OK]   ' + $m) -ForegroundColor Green }
function Write-Warn2([string]$m){ Write-Host ('  [WARN] ' + $m) -ForegroundColor Yellow }
function Write-Fail([string]$m) { Write-Host ('  [FAIL] ' + $m) -ForegroundColor Red }

# 工程自检：这一层必须直接含 app.json（导入时要选到这一层）
$appJson = Join-Path $ProjectRoot 'app.json'
$cfgJson = Join-Path $ProjectRoot 'project.config.json'

function Find-DevToolsCli {
    $cands = @()
    # 常见安装位置（含官方中文名与两种叫法）
    $cands += 'C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat'
    $cands += 'C:\Program Files\Tencent\微信web开发者工具\cli.bat'
    $cands += 'C:\Program Files (x86)\Tencent\微信开发者工具\cli.bat'
    $cands += 'C:\Program Files\Tencent\微信开发者工具\cli.bat'
    if ($env:LOCALAPPDATA) {
        $cands += (Join-Path $env:LOCALAPPDATA 'Programs\微信web开发者工具\cli.bat')
        $cands += (Join-Path $env:LOCALAPPDATA 'Programs\微信开发者工具\cli.bat')
    }
    if ($env:ProgramFiles)    { $cands += (Join-Path $env:ProgramFiles 'Tencent\微信web开发者工具\cli.bat') }
    if (${env:ProgramFiles(x86)}) { $cands += (Join-Path ${env:ProgramFiles(x86)} 'Tencent\微信web开发者工具\cli.bat') }
    # 非系统盘安装（实测本机 D: 在用，故一并探测，避免漏掉自定义安装位置）
    $cands += 'D:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat'
    $cands += 'D:\Program Files\Tencent\微信web开发者工具\cli.bat'
    $cands += 'D:\Tencent\微信web开发者工具\cli.bat'
    foreach ($p in $cands) { if ($p -and (Test-Path -LiteralPath $p)) { return $p } }

    # 兜底：在 Tencent 目录下浅层搜索（避免全盘递归太慢）
    foreach ($base in @('C:\Program Files (x86)\Tencent', 'C:\Program Files\Tencent', 'D:\Tencent', 'D:\Program Files (x86)\Tencent', 'D:\Program Files\Tencent')) {
        if (Test-Path -LiteralPath $base) {
            $hit = Get-ChildItem -LiteralPath $base -Recurse -Filter 'cli.bat' -ErrorAction SilentlyContinue |
                   Select-Object -First 1
            if ($hit) { return $hit.FullName }
        }
    }
    return $null
}

Write-Host ''
Write-Head 'TRPG 微信小程序客户端 —— 启动（导入微信开发者工具）'
Write-Head '===================================================='
Write-Host ('  工程目录：' + $ProjectRoot)

# ---- 0. 工程自检 ---------------------------------------------------------
if (-not (Test-Path -LiteralPath $appJson)) {
    Write-Fail ('缺少 app.json，本目录不是小程序工程根：' + $ProjectRoot)
    Write-Host '         请确认解压后目录层级完整。'
    exit 1
}
if (-not (Test-Path -LiteralPath $cfgJson)) {
    Write-Warn2 '未找到 project.config.json（不影响导入，但 AppID/设置需手工确认）。'
}
Write-Ok ('app.json 已找到（导入时请选到这一层：' + $ProjectRoot + '）')

# ---- 1. 探测开发者工具 cli.bat ------------------------------------------
Write-Host ''
Write-Host '[1/2] 正在查找微信开发者工具 ...'
$cli = Find-DevToolsCli

if (-not $cli) {
    Write-Host ''
    Write-Fail '未找到微信开发者工具（cli.bat）。'
    Write-Host ''
    Write-Host '  小程序不能由本地脚本直接弹出界面 —— 它必须由「微信开发者工具」编译载入。'
    Write-Host '  因此本包无法像 Web 客户端那样一键弹窗，需要你**先安装工具**。'
    Write-Host ''
    Write-Host '  说明：装了 Node.js 也不能替代 —— 小程序的编译与模拟器是 IDE 专有运行时，'
    Write-Host '        无法用 npm / node 安装或绕过。必须用微信开发者工具。'
    Write-Host ''
    Write-Host '  【第 1 步】安装微信开发者工具（只需一次）' -ForegroundColor Yellow
    Write-Host '     官方下载：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html'
    Write-Host '     选「稳定版 Stable Build」Windows 64 位，按默认选项安装。'
    Write-Host '     默认安装位置：C:\Program Files (x86)\Tencent\微信web开发者工具\'
    Write-Host ''
    Write-Host '  【第 2 步】安装后确认（应输出 True）：' -ForegroundColor Yellow
    Write-Host '     Test-Path "C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat"'
    Write-Host '     若为 False，请在工具内开启：设置 → 安全设置 → 服务端口（打开）'
    Write-Host '     开启后即会生成 cli.bat，命令行导入才可用。'
    Write-Host ''
    Write-Host '  【第 3 步】手工导入本项目（无需命令行）' -ForegroundColor Yellow
    Write-Host '     打开微信开发者工具 → 首页选「导入项目」（不是「新建项目」）'
    Write-Host ('     目录：' + $ProjectRoot)
    Write-Host '     AppID：选 touristappid 或点「测试号」；后端服务选「不使用云服务」'
    Write-Host '     点「导入」→ 首屏是「连接设置」页。'
    Write-Host ''
    Write-Host '  【第 4 步】勾选「不校验合法域名」' -ForegroundColor Yellow
    Write-Host '     工具右上角「详情」→「本地设置」→ 勾选'
    Write-Host '     「不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书」'
    Write-Host ''
    Write-Host '  更多说明见同目录《使用说明.txt》第二节与第九节。'
    Write-Host ''
    exit $EXIT_NOCLI
}

Write-Ok ('已找到：' + $cli)

# ---- 2. 用 cli 打开项目 --------------------------------------------------
Write-Host ''
Write-Host '[2/2] 正在用微信开发者工具打开本项目 ...'
Write-Host ('        命令：cli.bat open --project "' + $ProjectRoot + '"')

try {
    if ($Wait) {
        & $cli open --project $ProjectRoot
    } else {
        # cli 可能常驻，避免卡住当前窗口：失败才回退到同步等待
        $p = Start-Process -FilePath $cli -ArgumentList @('open', '--project', $ProjectRoot) -PassThru -ErrorAction Stop
        if ($p) { $null = $p.WaitForExit(20000) }
    }
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    if ($code -eq 0) {
        Write-Ok '已请求微信开发者工具打开项目（请查看工具窗口）。'
        exit $EXIT_OK
    }
    Write-Warn2 ('cli.bat 返回码 ' + $code + '，可能未成功打开项目。')
} catch {
    Write-Warn2 ('调用 cli.bat 失败：' + $_.Exception.Message)
}

Write-Host ''
Write-Host '  请手工导入：打开微信开发者工具 →「导入项目」→ 目录选到：' -ForegroundColor Yellow
Write-Host ('    ' + $ProjectRoot)
Write-Host '  并勾选「详情 → 本地设置 → 不校验合法域名」。'
Write-Host '  若 cli 报「未登录 / 服务端口未开启」，请在工具内开启：设置 → 安全设置 → 服务端口。'
Write-Host ''
exit $EXIT_FAILED

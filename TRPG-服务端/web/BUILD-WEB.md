# BUILD-WEB.md —— GM 端（/app）前端构建 SOP

> 适用：`TRPG-服务端/web/`（React + Vite + TypeScript）
> 产物：`TRPG-服务端/web/dist/`，由 FastAPI 以 `/app/` 静态托管
> 维护：implementer-gmui 建立（R2 轮次）　供 t2 / t4 复用

## 0. 为什么需要这份 SOP

本轮之前交付包内**没有** `web/src`，GM 端只能改已构建的 bundle，无法做真实 UI 改动。
现已把可构建源码纳入交付包（captain 决策 B），并**实测**该源码可逐字节复现线上 bundle。
但构建链上有 **3 个坑**，不按本 SOP 操作会**静默破坏线上功能**。

## 1. 源码位置（唯一权威副本）

```
TRPG-服务端/web/
  src/                 ← 前端源码（32 文件）
  public/assets/theme-cnmods.css   ← R32 主题覆盖层（vite 原样拷贝，不 hash）
  scripts/             ← 构建后处理 + UI 检查脚本
  index.html           ← vite 入口
  package.json / package-lock.json / tsconfig.json
  vite.config.ts / tailwind.config.js / postcss.config.js / eslint.config.js
```

**不含** `node_modules/`（119 MB，按需 `npm ci` 生成）。
**不要**在 `trpg_run\dev\trpg\web`（历史镜像）上改动；以交付包内这份为准。

## 2. 标准构建流程（远程 110）

```powershell
# ① 在 TEMP 副本里构建 —— 绝不在交付目录内跑 npm（会污染交付包）
$web = 'C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端\web'
$b   = Join-Path $env:TEMP 'gmweb-build'
if (Test-Path $b) { Remove-Item $b -Recurse -Force }
robocopy $web $b /E /XD node_modules dist dist-preview .pytest_cache __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
Set-Location $b

# ② 依赖 + 构建（build:remote = tsc --noEmit && vite build && node scripts/ensure-theme-order.mjs）
npm ci --no-audit --no-fund
npm run build:remote
```

> ⚠️ **不要用 `npm run build`**。它末步是 `node scripts/copy-keeper-ui.mjs`，该脚本的源路径
> （`E:\dsh3080\app\node_modules\.pnpm` 与 `<workspace>/trpg_agent/vendor/dsh-017-keeper/ui`）
> **在远程 110 上都不存在**（实测均 False），会直接抛错。用 `build:remote`。

## 3. ⚠️ 三个必须知道的坑

### 坑 1：`vite build` 会**清空 `dist/`** —— 会删掉线上的 `keeper-ui/`

Vite 默认 `emptyOutDir: true`（`outDir` 在项目根内）。而 `dist/keeper-ui/` 是**线上正在服务的功能**
（实测 `/app/keeper-ui/index.html` → 200，7,307 B；106 文件 / 8,033,327 B；
GM bundle 内引用 `/app/keeper-ui` 2 处、`keeper-ui` 6 处、`iframe` 4 处 —— DshPanel 内嵌）。

**原本由 `copy-keeper-ui.mjs` 在构建后补回，但该脚本在远程跑不了（见上）。**

⇒ **部署前必须备份、部署后必须还原**：
```powershell
# 部署前
robocopy (Join-Path $web 'dist\keeper-ui') (Join-Path $env:TEMP 'keeper-ui-backup') /E /NFL /NDL /NJH /NJS /NP | Out-Null
# 构建产物落到 dist 之后
robocopy (Join-Path $env:TEMP 'keeper-ui-backup') (Join-Path $web 'dist\keeper-ui') /E /NFL /NDL /NJH /NJS /NP | Out-Null
```

### 坑 2：R32 主题覆盖层的**加载顺序**

`public/assets/theme-cnmods.css` 必须在 bundle CSS **之后**加载才能生效（同优先级靠后覆盖，且 t4 明确不用 `!important`）。
但 vite 会把入口 script 与 bundle CSS 追加到 `<head>` 末尾 ⇒ 源码里写的主题 `<link>` 会**排到 bundle CSS 之前**，R32 失效。
⇒ `npm run build:remote` 末步的 `scripts/ensure-theme-order.mjs` 会把主题 `<link>` 移回 `</head>` 之前。**幂等**，可重复执行。

### 坑 3：历史 hash 产物与旧 dist

`dist/assets/` 现有 **5 个文件，全部被 `dist/index.html` 引用**（未引用 = 0）；`dist/dist/` **已不存在**。
（历史时点：31 个资产 / 26 个未被引用 ≈ 5,778,988 B；`dist/dist/` 105 文件 / 6,853,146 B —— 均已于构建 #1/#2 清理，见 `BUILD-LOG.md`。）
部署后按"只留本次构建实际引用的一套"清理：
```powershell
$refs = [regex]::Matches((Get-Content (Join-Path $web 'dist\index.html') -Raw -Encoding UTF8), 'assets/([A-Za-z0-9_.\-]+)') | ForEach-Object { $_.Groups[1].Value }
Get-ChildItem (Join-Path $web 'dist\assets') -File | Where-Object { $refs -notcontains $_.Name } | Remove-Item -Force
Remove-Item (Join-Path $web 'dist\dist') -Recurse -Force   # 旧树残留
```

## 4. 部署与验证（"构建成功" ≠ "线上生效"）

```powershell
# 产物落回交付目录
robocopy (Join-Path $b 'dist') (Join-Path $web 'dist') /E /NFL /NDL /NJH /NJS /NP | Out-Null
# 还原 keeper-ui（坑 1）
robocopy (Join-Path $env:TEMP 'keeper-ui-backup') (Join-Path $web 'dist\keeper-ui') /E /NFL /NDL /NJH /NJS /NP | Out-Null
# 清历史产物（坑 3）
...见上...

# 验证（静态托管，无需重启服务端）
foreach ($u in @('/app/','/app/assets/index-DsfUF84T.js','/app/assets/index-DAU2_EXr.css','/app/assets/theme-cnmods.css','/app/keeper-ui/index.html')) {
  try { $r = Invoke-WebRequest ('http://127.0.0.1:9211' + $u) -UseBasicParsing -TimeoutSec 10; "$u -> $($r.StatusCode) len=$($r.RawContentLength)" }
  catch { "$u -> $($_.Exception.Response.StatusCode.value__)" }
}
```
**判据**：`/app/` 200 且引用到的每个 asset 均 200；`theme-cnmods.css` 200 且 `index.html` 中它排在 bundle CSS 之后；
`/app/keeper-ui/index.html` 200（未回归）。改动后请在汇报里贴出这些原始输出。

## 5. 连接配置与已知行为

### 5.1 GM 端已接真服务端（t11，P0 已修复）

**不再需要改代码即可换牌桌** —— 连接参数支持运行时 URL 覆盖（构建期 env 仅作默认值）：

```
http://<host>:9211/app/?table=<table_id>&viewer=<viewer>&role=kp|pl|spectator&campaign=<campaign_id>&token=<webapp-token>#/kp
```
- 查询串写在 hash 之前或之内均可（`#/kp?table=x` 也支持）。
- 省略时回退：`table=tbl_demo`、`viewer=kp`、`role=kp`、`campaign=camp-mist-port`。
- WS 基址默认取**同源** `ws(s)://<当前 host:port>`（不再硬编码 9210）；可用 `?ws=ws://host:port` 覆盖。
- 只开启 real 模式的构建期开关：`web/.env.production` 的 `VITE_TRPG_TRANSPORT=real`。

**横幅是状态驱动的**（`src/lib/transport.ts` 的 `subscribeStatus`/`transportStatusLabel`）：
`open` → 「已连接服务器（实时同步）」；`reconnecting` → 「连接中断，正在重连…（本地改动暂存，恢复后同步）」；
`closed` → 「连接已关闭：改动不会同步到服务器（降级为单机演示）」。
DOM 上有 `data-conn-mode` / `data-conn-status` 属性，便于自动核验。

### 5.2 当前产物 hash 基线（**2026-09-27 现场复算**）

`web/dist/assets/` 现有 **5 个文件，全部被 `web/dist/index.html` 引用**（未引用 = 0）：

| 文件 | 字节 | sha256 |
|---|---|---|
| `index-DsfUF84T.js` | 96,095 | `f860d8e0d9c109cfca4fdf97ea6a9f866851c08a3fe46b55e8e4ac080f4118ea` |
| `index-DAU2_EXr.css` | 20,650 | `4bb3b8de816ad2f89f2a7e73b9263e996cd479e61274baa3a4a4c6b933c468ac` |
| `vendor-BmIzTfB1.js` | 260,623 | `4ed4b06b355b7fe2b9b2ea9d4ccb8a37fcb1aca1be8092ff99de47baabc1407b` |
| `vendor-konva-BonOWF5a.js` | 198,322 | `c4233e0d4cfaf3488a7acaf87022ba1ebe3991acf525e6869d0c06cb2166ce50` |
| `theme-cnmods.css` | **18,674** | `4e77a95b0e2b8377c288d97b172f8dd3b9e43b9050a23cfe567602af0c1bd2ac` |

> ⚠️ **本表旧值已作废（`index-VVtlFbKo.js` / `index-CKy9f5S6.css` / `vendor-DzJ6bdjk.js` / `vendor-konva-BMkByC4X.js` / `theme-cnmods.css 5534e0d3…`）**：前四者属 **t11 / 构建 #1–#2 时点**，现已不在 `dist/assets/` 内（I1/I2/I3/I4 判据见 `BUILD-LOG.md` §0）；`theme-cnmods.css` 的 `8,732 B / 5534e0d3…` 是 **构建 #3 时点观测值**，该文件后被 R2-P2 触击目标改动（`min-height` 34→44px），现行值 **18,674 B / 4e77a95b…**。
> 历史时点值一律以 `BUILD-LOG.md` §1 / §2b 的「时点观测值（仅记录，不作断言）」段落为准。
> `index-*.js` 与 `index-*.css` 的内容哈希随源码变化；**css/vendor/theme 未动源码时应保持不变**。
> 源码未改动时重建应得同一组 hash（已验证）。

## 6. 现成的 UI 检查脚本（勿重复造轮子）

`web/scripts/` 里已有（node 直接跑，无额外依赖）：
- `contrast-check.mjs`（1,931 B）—— 对比度检查（R33/R34 配色判据）
- `nav-overlap-check.mjs`（1,309 B）—— 导航重叠/遮挡几何检查（R33 碰撞）
- `theme-sweep.mjs`（3,328 B）—— 主题令牌巡检（R32 三端一致）
- `check_realTransport.ts`（5,842 B）—— 传输层切换自检（R12）

## 7. 并发纪律（重要）

`web/dist/` 是**构建单出口**：谁构建谁覆盖。
⇒ 同一时刻只允许一人构建+部署；部署后立刻复核 §4 的 5 个 hash 并登记在汇报里。
⇒ 若你只改了源码没部署，请明确说明"未部署"，避免他人以为线上已生效。

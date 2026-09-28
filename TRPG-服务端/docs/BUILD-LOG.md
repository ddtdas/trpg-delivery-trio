# GM 端构建登记表（BUILD-LOG）

> 维护者：implementer-gmui（规则 2 / 纪律 D：GM 前端源码树与 `web/dist` 的唯一写入者与唯一构建者）
> 本表按**验收规范第 4 条**编排：区分【不变量（可断言）】与【时点观测值（仅记录）】，绝不混用。

## 0. 可复算的不变量（**这才是判据**）

任何人可在权威包上独立复算，**不需要相信本表抄的任何数字**：

```powershell
# 权威包路径：<Desktop>\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端\
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\r2_dist_integrity.ps1
```

脚本断言的是 **dist 内部自洽性**（对重新构建免疫、对内容变化免疫）：

| ID | 不变量 | 为什么它是真判据 |
|---|---|---|
| I1 | `index.html` 引用的每个 `/app/assets/<name>` 都真实存在 | 抓「引用了不存在的产物」 |
| I2 | `assets/` 中每个文件都被引用（`theme-cnmods.css` 豁免） | **抓「陈旧 hash 死产物」** |
| I3 | `index-*.js` 恰好 1 个 | 同上（本项曾实测 15 个） |
| I4 | `index-*.css` 恰好 1 个 | 同上（本项曾实测 8 个） |
| I5 | `dist/dist` 不存在 | 抓重复树 |
| I6 | `dist/keeper-ui` 存在且非空 | **抓「vite build 清空 dist 静默删掉线上功能」** |
| I7 | `theme-cnmods.css` 位于 bundle CSS **之后** | **抓「bundle 覆盖 R32 主题」** |

**最近一次复算（构建 #2 之后）**：
```
PASS  I1  index.html refs all exist  [5 refs]
PASS  I2  no unreferenced dead artifacts  [5 files]
PASS  I3  exactly one index-*.js  [count=1]
PASS  I4  exactly one index-*.css  [count=1]
PASS  I5  dist/dist absent
PASS  I6  keeper-ui present and non-empty  [files=106]
PASS  I7  theme after bundle CSS (R32 wins)  [bundle=0 theme=1]
RESULT: ALL INVARIANTS HOLD (fail=0)
```

## 1. 时点观测值（**仅记录，不作断言**）

> 产生命令：`Get-FileHash -LiteralPath <file> -Algorithm SHA256`（每行附 `len=` 自检，应为 64）
> ⚠️ 这些值**随内容变化而变**（本表 #1→#2 已变过一次）。**硬编码它们与硬编码字节 sha256 是同构错误**，只是周期更长。**请勿作为断言使用。**

### 构建 #2 观测（页头 chip 去硬编码）

| 资产 | 字节 | sha256 | len |
|---|---|---|---|
| `assets/index-BUCDjFsz.js` | 90,828 | `8e95e2af73fff9737f73de7d0da4616badb8ad192c897ad7c0de55c683018bf0` | 64 |
| `assets/index-CKy9f5S6.css` | 19,779 | `06ac490dbc8e4bb0214736304e723450d8c5aad9bcdbe12e0616f6e6098104e9` | 64 |
| `assets/theme-cnmods.css` | 8,732 | `5534e0d36ea94ad56540159285652cefdfba17c5f2d87d19ddc198f3d7f115a4` | 64 |
| `assets/vendor-DzJ6bdjk.js` | 260,616 | `c6b28ddfe6f70ac2067e290f85a6370fc1ed3c6cecdbf6de9f7b68bdff3c1cf2` | 64 |
| `assets/vendor-konva-BMkByC4X.js` | 198,322 | `17217555abed315d3a9945013d7ad06a5f4b5c74952938517fcc549ac86b233f` | 64 |
| `dist/index.html` | 769 | `a69c4c2c74d032520867135511ae3fe008bfec43b09530ab9a10f70fae4fdca0` | 64 |

### 构建 #1 观测（t11 主交付）
`index-VVtlFbKo.js` `d5d313d6581fabf8cb91e9f070fdf19ba39c99bed17f1bca81eb6455622f2b45`（**已被 #2 替换**）；
`index.html` `d82869ab4f09ba18a108cebeebd2da211985db860c39fa93d3df5504d39af9e2`；清理 27 个历史 asset（5,868,053 B）+ `web/dist/dist`。


## 2b. 构建 #3（R5 GM 单窗口总览 UI）

**动机**：R5 需要 GM 端单窗口总览（六块），且「首屏无滚动无重叠」是 **UI 判据**，光有服务端 API 判不了 PRESENT。
**改动**：新增 \`src/components/Overview.tsx\`（自包含：从本页 URL 取 campaign/token，\`fetch\` 服务端权威总览）；\`App.tsx\` 加导航入口「GM 总览」与路由 \`/overview\`。
**不改** \`transport.ts\` / \`realTransport.ts\`（t11 核心文件）——组件自取参数，零风险。

**布局为何能保证「无滚动无重叠」**：外层高度钉死视口 + 六块 CSS Grid 固定 3×2 + **每块内部 \`overflow:auto\`**（溢出被约束在块内，页面本身不产生滚动）+ 子项 \`min-h-0\`（grid 子项默认 \`min-height:auto\` 会撑破容器，**这正是「重叠」的常见成因**）。

**可复算的 DOM 断言**（对重建与内容变化都免疫，符合验收规范第 4 条）：
\`\`\`js
document.querySelectorAll('[data-r5-block]').length === 6
document.documentElement.scrollHeight <= window.innerHeight + 1
!document.querySelector('[data-r5-degraded]')
\`\`\`

**实测**（CDP \`Emulation.setDeviceMetricsOverride\` 真实改视口）：
\`\`\`
1366x768 : blockCount=6 pageScrollsY=false pageScrollsX=false overlaps=0 overflowRight=0 overflowBottom=0
1920x1080: blockCount=6 pageScrollsY=false pageScrollsX=false overlaps=0 overflowRight=0 overflowBottom=0
\`\`\`
六块均渲染服务端真实数据（t7e2e_live：map_library / 2 玩家 / 回合 1 CLOSED 2/2 / 2 条待审 / 事件游标 408）。

**构建**：\`%TEMP%\gmbuild7\` 副本 \`npm run build:remote\`（tsc --noEmit && vite build && ensure-theme-order\）exit=0。
**过程中 tsc 拦下真错误**：\`export default\` 却用 \`import { Overview }\` ⇒ TS2614。**这是 \`tsc --noEmit\` 不可去掉的价值**。

**部署**：additive 复制 5 个资产 + index.html；定向删除 4 个陈旧 hash
\`index-BUCDjFsz.js / index-CKy9f5S6.css / vendor-DzJ6bdjk.js / vendor-konva-BMkByC4X.js\`。
**不变量**\`r2_dist_integrity.ps1\` → PASS I1..I7，**ALL INVARIANTS HOLD**（keeper-ui 106 文件仍在）。
**回滚点**：\`%TEMP%\dist-rollback-t8a\index.html\`（构建 #2）。

**时点观测值**（**仅记录，不作断言**；命令 \`Get-FileHash -LiteralPath <file> -Algorithm SHA256\`，len 自检=64）：
\`\`\`
f860d8e0d9c109cfca4fdf97ea6a9f866851c08a3fe46b55e8e4ac080f4118ea  len=64   96095  assets\index-DsfUF84T.js
4bb3b8de816ad2f89f2a7e73b9263e996cd479e61274baa3a4a4c6b933c468ac  len=64   20650  assets\index-DAU2_EXr.css
5534e0d36ea94ad56540159285652cefdfba17c5f2d87d19ddc198f3d7f115a4  len=64    8732  assets\theme-cnmods.css
4ed4b06b355b7fe2b9b2ea9d4ccb8a37fcb1aca1be8092ff99de47baabc1407b  len=64  260623  assets\vendor-BmIzTfB1.js
c4233e0d4cfaf3488a7acaf87022ba1ebe3991acf525e6869d0c06cb2166ce50  len=64  198322  assets\vendor-konva-BonOWF5a.js
83a94aaf0cf2ca38efe33d77228b367c18f6ca058321a011bc2d72bebf9ca445  len=64     769  index.html
\`\`\`

## 2. 构建 #2 变更说明

**动机**：tester 探针报「界面战役是 mock 的 `camp-mist-port`」。
**根因不是传输层** —— `App.tsx` 页头 chip 是**硬编码字符串**，已接真服务端仍显示 mock 战役名
⇒ 该读数**无论 mock/real 恒为 camp-mist-port**，是无效判据。
**改动**：chip 显示实际解析出的战役/牌桌，新增可探针属性 `data-campaign` / `data-table` / `data-conn-source`。

**构建**：`npm ci` → `npm run build:remote`（`tsc --noEmit && vite build && node scripts/ensure-theme-order.mjs`），exit=0。
**构建目录**：`%TEMP%\gmbuild6`（自 `TRPG-服务端\web` robocopy，排除 node_modules/dist）。

**⚠️ 绝不在交付目录 in-place 跑 `vite build`**：它默认清空 `dist/`，会**静默删掉 `dist/keeper-ui/`（106 文件 / 8 MB，线上正在服务）**，
而恢复它的 `scripts/copy-keeper-ui.mjs` 依赖两个**远程不存在**的路径 ⇒ **远程无法恢复**。
SOP = `%TEMP%` 副本构建 → **additive 部署** → 定向删除陈旧 hash（I1/I2/I3/I4 正是为此设的判据）。

**部署**：additive 复制 `index-BUCDjFsz.js` + `index.html`；定向删除陈旧 `index-VVtlFbKo.js`（90,599 B）。

**运行时实测**（space `trpg-r2-gmui-t11b`，`campaign=t7e2e_live`）：
- `data-conn-mode="real"` `data-conn-status="open"` `data-conn-label="chip-ok"` ← **WS 已连的直接证据**（该标签仅由 WS onopen 置位）
- 横幅「已连接服务器（实时同步）」；chip `CoC7 · t7e2e_live · t7e2e_live`、`data-conn-source="server"`
- R32 主题仍生效：`bodyBg=rgb(16,16,20)`、`--bg=#101014`

**回滚点**：`%TEMP%\dist-rollback-t11b\index.html`（构建 #1 的 index.html）

**受影响需重载**：tester（重跑 t11 探针做前后对照）、t4（GM 截图需重取）、implementer-ui。

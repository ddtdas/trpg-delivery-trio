# UI-TOKENS-MODU.md —— 魔都视觉语言令牌（R32 三端统一）

> 令牌源：`tokens.json` v2.0（`TRPG-服务端/player-web/tokens.json`，与 `TRPG-Web客户端/client/tokens.json` 逐字节相同）
> 参考站：<https://www.cnmods.net/web/>（魔都TRPG 主站，Vue3 + Naive UI + Tailwind，暗色主题）
> 提取方式：**运行时实测**（ego-browser / Chrome + `getComputedStyle`）＋ 站点 CSS/JS 主题覆盖静态核验
> 提取时间：2026-09-27 (+08:00)

---

## 1. 提取方法（可复现）

参考站是 Vue SPA，直接抓 HTML 只能拿到外壳，**必须打开渲染后的页面读计算样式**。

1. 打开 <https://www.cnmods.net/web/>，等待 SPA 挂载完成。
2. 读 `document.body` / `:root` 的计算样式与 `document.styleSheets`。
3. 抓取站点自身样式表与脚本：
   - `/web/assets/index-7b465a02.css`（Tailwind 产物 + 站点自定义规则）
   - `/web/assets/HomeView-228c094b.css`
   - `/web/assets/index-e1489138.js`（含 **App.vue 的 Naive UI themeOverrides**）
4. 逐组件读取计算样式：`header / .n-input / .n-button / .n-tag / .n-tabs / .n-pagination-item /
   .n-checkbox-box / .n-radio__dot / .n-base-selection / .n-scrollbar-rail / .n-divider`。
5. 用 Tailwind 任意值类（`bg-[#141c23ba]`、`h-[44px]` …）交叉核对几何尺寸。

**关键发现**：站点在 `App.vue` 里只覆盖了 4 个 Naive UI common 变量，其余全部沿用 `darkTheme` 默认暗色板。

```js
// /web/assets/index-e1489138.js（App.vue 的 themeOverrides，原文）
const t = { common: {
  fontFamily: "HarmonyOS",
  primaryColor: "#FFBB70",
  primaryColorHover: "rgb(250,197,131)",
  primaryColorPressed: "rgb(219,164,94)",
  inputColor: "#212625"
}};
theme: darkTheme
```

---

## 2. 实测取值（运行时 `getComputedStyle`）

### 2.1 根与排版

| 项 | 实测值 | 来源 |
|---|---|---|
| `body` background | `rgb(16, 16, 20)` = `#101014` | 计算样式（= darkTheme `neutralBody`） |
| `body` color | `rgba(255, 255, 255, 0.82)` | 计算样式（= `textColor2` / `alpha2`） |
| `body` font-family | `HarmonyOS` | 计算样式 + `@font-face{font-family:HarmonyOS;src:url(HarmonyOS_Sans_SC_Regular-*.ttf)}` |
| `body` font-size | `14px` | 计算样式（= `fontSize`） |
| `body` line-height | `22.4px` = 14 × **1.6** | 计算样式（= `lineHeight: 1.6`） |
| `html` min-width | `1440px` | 站点 CSS（桌面优先） |

### 2.2 颜色（全部为实测/静态核验值）

| 令牌 | 值 | 实测证据 |
|---|---|---|
| bg | `#101014` | body 计算背景 `rgb(16,16,20)` |
| card / panel（不透明形态） | `#141c23` | 首页侧栏 `w-[290px] bg-[#141C23]` → 计算 `rgb(20,28,35)`，radius **0**，blur none |
| cardTranslucent（半透明面板） | `rgba(20,28,35,0.73)` | `/web/moduleDetail` 面板 `bg-[#141c23ba] backdrop-blur rounded` → 计算 `rgba(20,28,35,0.73)` + `backdrop-filter: blur(8px)` + radius **4px** + **border 0px** + **box-shadow none** |
| input | `#212625` | `.n-input` 计算背景 `rgb(33,38,37)`（= themeOverrides `inputColor`） |
| topbar | `#262c31` | `header` 计算背景 `rgb(38,44,49)` |
| divider | `#32383e` | `header` 计算 `border-bottom: 1px solid rgb(50,56,62)` |
| text | `rgba(255,255,255,0.82)` | body / `.n-input__input-el` 计算色 |
| muted | `#b9b9b9` | `header` 计算色 `rgb(185,185,185)` |
| border | `rgba(255,255,255,0.24)` | darkTheme `alphaBorder: 0.24`；`.n-radio__dot` 计算 `inset 0 0 0 1px rgba(255,255,255,0.24)` |
| accent | `#ffbb70` | themeOverrides `primaryColor`；`.n-tabs-bar` 计算背景 `rgb(255,187,112)` |
| accentHover | `#fac583` | themeOverrides `primaryColorHover: rgb(250,197,131)` |
| accentPressed | `#dba45e` | themeOverrides `primaryColorPressed: rgb(219,164,94)` |
| accentText | `#3d1b00` | `.router-link-active` 计算色 `rgb(61,27,0)`（琥珀底上的文字） |
| chipBg | `#212625` | 同 input（站点唯一的小面积实底） |
| hover | `rgba(255,255,255,0.09)` | darkTheme `alphaPending: 0.09`；`.n-divider` 计算背景 `rgba(255,255,255,0.09)` |
| action | `rgba(255,255,255,0.06)` | darkTheme `alphaAction: 0.06`；`.n-pagination-item` 计算背景 `rgba(255,255,255,0.06)` |
| placeholder / textDisabled | `rgba(255,255,255,0.38)` | darkTheme `alpha4: 0.38` |
| textStrong | `rgba(255,255,255,0.90)` | darkTheme `alpha1: 0.9`；`.n-tabs-tab` 计算色 |
| avatarBg | `rgba(255,255,255,0.18)` | `.n-avatar` 计算背景 `rgb(66,66,69)`（= 0.18 白叠 `#101014`） |
| skeleton | `rgba(255,255,255,0.125)` | `.n-skeleton` 计算背景 |
| modal / popover | `#2c2c32` / `#48484e` | darkTheme `neutralModal` / `neutralPopover` |
| ok / warn / err | `#63e2b7` / `#f2c97d` / `#e88080` | darkTheme `successDefault` / `warningDefault` / `errorDefault` |
| gold / goldDeep / cream | `#ffca58` / `#ffb542` / `#e4caa5` | 站点 Tailwind 色类 `.text-[#FFCA58]` `.text-[#FFB542]` `.text-[#E4CAA5]` |
| ink 系 | `#783100` / `#462500` / `#623200` / `#3d1b00` | 站点 Tailwind 色类 + 模块卡实测（羊皮纸底棕字） |
| link | `#57a7ff` | 站点 Tailwind 色类 `.text-[#57A7FF]` |
| footerBg | `rgba(0,0,0,0.37)` | 页脚 `bg-[#0000005e]` → 计算 `rgba(0,0,0,0.37)`，高 70px |

> **派生值（非实测，公式已注明）**：`errBarBg = rgba(232,128,128,0.10)`、`errBarBorder = rgba(232,128,128,0.32)`
> —— 取实测 `errorColor #e88080`，透明度沿用站点实测的 alpha 填充惯例（`alphaInput 0.1` / `alphaBorder 0.24`）。
> `shadow.focusGlow = 0 0 8px rgba(255,187,112,0.30)` 为本项目自有的输入焦点柔光（站点用 2px outline）。

### 2.3 圆角 / 间距 / 字号阶 / 尺寸

| 类别 | 实测值 |
|---|---|
| 圆角 | 控件 **3px**（`borderRadius`：`.n-input` `.n-button` `.n-base-selection` `.n-pagination-item` 计算值）；小元素 **2px**（`.n-tag` `.n-checkbox-box` 计算值）；面板 **4px**（Tailwind `.rounded` = 0.25rem，侧栏面板计算值）；圆形 **50%**（`.n-avatar` `.n-radio__dot`） |
| 间距 | 站点**无间距阶**（Tailwind 任意值）。实测簇：4 / 8 / 12 / 16 / 18 / 20 / 24 / 30 / 42 / 48。本项目保留 v1.31 的 4/8/12/16/24 阶 |
| 字号 | 11 / 12 / 14 / 15 / 16 / 18 / 20（Tailwind 计算值分布：14px×457、18px×68、16px×40、11px×6、20px×5） |
| 字重 | 400（normal）/ 500（`fontWeightStrong`）/ 600 / 700（`.font-bold` 实测） |
| 控件高度 | mini 16 / tiny 22 / small 28 / medium 34 / large 40 / huge 46（Naive UI `height*`，`.n-button--small-type` 计算 28px、medium 计算 34px） |
| 其它尺寸 | header 44px；header 导航项 80×40；搜索框 34px；头像 34×34；滚动条 5px；页脚 70px；内容列 1120px；侧栏 260px |
| 网格 | 模块卡网格 `grid-cols-3 gap-[20px]`（搜索页 360×236 卡）/ `grid-cols-6 gap-[12px]`（首页 230×307 卡） |

### 2.4 阴影与动效

| 项 | 实测值 |
|---|---|
| 运行时可观测阴影 | **全部为 `none`**（`box-shadow` 统计为空；站点不用投影做层次，用实底色 + 1px 描边） |
| 浮层阴影（库内定义） | popover `0 1px 2px -2px rgba(0,0,0,.24), 0 3px 6px 0 rgba(0,0,0,.18), 0 5px 12px 4px rgba(0,0,0,.12)`；modal `0 3px 6px -4px rgba(0,0,0,.24), 0 6px 12px 0 rgba(0,0,0,.16), 0 9px 18px 8px rgba(0,0,0,.10)`；float `0 6px 16px -9px rgba(0,0,0,.08), 0 9px 28px 0 rgba(0,0,0,.05), 0 12px 48px 16px rgba(0,0,0,.03)` |
| 缓动 | `cubic-bezier(.4, 0, .2, 1)` —— 全站唯一缓动（`transition-timing-function` 计算值统计） |
| 时长 | `.15s`（Tailwind `.transition` 默认）/ `.2s`（tabs 指示条、路由切换）/ `.3s`（Naive 组件默认）/ `.5s`（页面级颜色过渡） |
| 路由切换 | `@keyframes route-transition{0%{transform:translateY(10px);opacity:0} to{opacity:1}}`，`animation: .2s` |
| 模糊 | `backdrop-filter: blur(8px)`（`bg-[#141c23ba] backdrop-blur` 面板） |

### 2.5 组件形态

| 组件 | 实测规格 |
|---|---|
| 顶栏 header | 高 44px（1440×44 实测），背景 `#262c31`，下边框 `1px solid #32383e`，文字 `#B9B9B9`，`box-shadow: none` |
| 顶栏导航项 | `80×40` 居中，**radius 0**，字号 16px/400，常态文字 `#b9b9b9`；**激活项 = 金色底（`nav_bg-*.png` 贴图）+ 墨色字 `rgb(61,27,0)` = #3d1b00**（`.router-link-active` 实测） |
| 输入框 | 高 34px，背景 `#212625`，圆角 3px，字号 14px/21px，文字 `rgba(255,255,255,0.82)`；`.n-input__border` 计算值 `1px solid rgba(0,0,0,0)` → **默认无可见边框**，聚焦才显 primary 边框 |
| 按钮（默认型 default） | 高 34px，**背景 `rgba(0,0,0,0)` 全透明**，**border 0px**（`.n-button__border` 子元素不存在），圆角 3px，内边距 `0 14px`，字号 14px/400，`box-shadow: none` |
| 按钮（小） | 高 28px，圆角 3px，内边距 `0 10px` |
| 标签 n-tag | 高 22px，圆角 **2px**，字号 12px/12px，内边距 `0 7px` |
| 面板 / 卡片 | 背景 `rgba(20,28,35,0.73)` + `backdrop-filter: blur(8px)`，圆角 **4px**，**border 0px**，**box-shadow none**，内边距 `31px 23px`（`/web/moduleDetail` 实测，两个实例 830×84 与 280×720） |
| 模块卡 | 360×236（搜索页）/ 230×307（首页），背景为羊皮纸贴图，文字 `#783100`，标题 16px/700 `#462500` 居中、`margin-bottom 9px` |
| 标签页 n-tabs | tab 高 41px，内边距 `10px 0`，字号 14px/21px；指示条高 **2px**、背景 `#ffbb70` |
| 分页项 | 28×28，圆角 3px；常态背景 `rgba(255,255,255,0.06)`、文字 `rgba(255,255,255,0.38)`；激活态文字 `#ffbb70` + 边框 `1px solid rgba(255,187,112,0.52)` |
| 复选框 | 16×16，圆角 2px |
| 单选框 | 16×16，圆角 50%，内阴影 `inset 0 0 0 1px rgba(255,255,255,0.24)` |
| 下拉选择 | 高 28px（small），圆角 3px |
| 头像 | 34×34，圆角 50%，背景 `rgba(255,255,255,0.18)` |
| 垂直分隔线 | 1×16，背景 `rgba(255,255,255,0.09)` |
| 滚动条 | 宽/高 5px，圆角 5px |
| 焦点态 | `outline: 2px solid #ffbb70; outline-offset: 2px` |
| 层次手段 | **全站运行时 `box-shadow` 统计为空**（8 个页面/视图实测 0 个带阴影元素）；层次 = 背景色差 + `backdrop-filter: blur(8px)`。这是该站最关键的风格特征 |

---

## 3. 三端落地映射

| 端 | 令牌落地文件 | 组件落地文件 | 加载方式 |
|---|---|---|---|
| GM 端（`/app`） | `web/dist/assets/theme-cnmods.css`（`:root` 覆盖） | 同文件 §4–§7 | `web/dist/index.html` 在 bundle CSS **之后**追加 `<link>` |
| TRPG-Web 客户端 | `TRPG-Web客户端/client/tokens.json` | `TRPG-Web客户端/client/app.css`（`:root`） | 零构建，直接引入 |
| 玩家端（`/player/`） | `player-web/tokens.json`（与上者逐字节相同） | `player-web/app.css`（与上者逐字节相同） | 零构建，直接引入 |
| 微信小程序 | `TRPG-微信小程序客户端/tokens.wxss` | `TRPG-微信小程序客户端/app.wxss`（`@import "tokens.wxss"`） | WXSS 自定义属性 |

**契约兼容**：`docs/CROSS-END-CONTRACT.md` §2 的键名集合**未改动**，仅换值；新增键为增量追加。
小程序侧保留契约驼峰别名（`--color-accentText` / `--color-chipBg` / `--color-errBarBg` /
`--color-errBarBorder` / `--layout-maxWidth` / `--layout-navHeight` / `--layout-tapMin`）。

---

## 4. 相对 v1.31 的差异（换值清单）

| 令牌 | v1.31 | v2.0（实测） | 说明 |
|---|---|---|---|
| color.bg | `#17191a` | `#101014` | v1.31 值在参考站不存在（自拟）；实测 body 为 `rgb(16,16,20)` |
| color.card | `#212625` | `#141c23` | `#212625` 实为 `inputColor`（现独立为 `color.input`）；面板实为 `#141C23` |
| color.border | `rgba(255,255,255,0.14)` | `rgba(255,255,255,0.24)` | darkTheme `alphaBorder` |
| color.accentText | `#1a1206` | `#3d1b00` | 实测激活态文字色 |
| color.chipBg | `#2b3237` | `#212625` | v1.31 值不存在；改用实测小面积实底 |
| color.accentHover | `#f5d599` | `#fac583` | 实测 `primaryColorHover` |
| color.errBarBg/Border | `#2a1f20` / `#4a2f31` | `rgba(232,128,128,0.10)` / `rgba(232,128,128,0.32)` | 改为由实测 `errorColor` + 实测 alpha 惯例派生 |
| radius.card | `6px` | `4px` | 实测面板 `.rounded` |
| radius.ctl | `4px` | `3px` | 实测 `borderRadius` |
| radius.chip | `999px` | `2px` | 参考站**无胶囊形**；实测 `n-tag` 为 2px |
| font.h2 | `15px` | `16px` | 实测标题为 16px |
| layout.navHeight | `48px` | `44px` | 实测 header 高 44px |
| font 栈 | `v-sans, system-ui, …` | `HarmonyOS, system-ui, …` | 实测字体族；HarmonyOS 为参考站自托管字体，本项目不随包分发，缺失时回退系统 CJK 字体 |
| 行高 | `1.5` | `1.6` | 实测 `lineHeight: 1.6`（22.4px / 14px） |
| 缓动 | `ease` | `cubic-bezier(0.4, 0, 0.2, 1)` | 实测全站唯一缓动 |
| 过渡时长 | `.15s` | `150ms`（同名同值，令牌化） | 数值未变，改为引用令牌 |
| GM 端主题 | 浅色（`#f5f6f7`/`#ffffff`/`#111827`，圆角 8px，字号 16px） | 魔都暗色 | 三端统一的**主要差距**，由 `theme-cnmods.css` 覆盖层解决 |
| 面板形态 | `#212625` 不透明 + 1px 描边 | `rgba(20,28,35,0.73)` + `blur(8px)`，无描边 | 见 §7 对账 R1 |
| 次要按钮 | 半透明底 + 1px 描边 | **全透明底、无描边**，padding `0 14px` | 见 §7 对账 R2 |
| 输入框 | 1px 可见描边 | 默认无可见描边（`1px solid rgba(0,0,0,0)`），聚焦才显色 | 见 §7 对账 R3 |
| 导航激活态 | 强调色文字 + 透明底 | **金底 + 墨色字** | 见 §7 对账 R4 |

**新增键**（增量）：`color.{input,topbar,divider,modal,popover,textStrong,textDisabled,placeholder,hover,action,avatarBg,skeleton,accentPressed,accentSoft,gold,goldDeep,cream,ink,inkStrong,inkMid,inkActive,link}`、
`radius.{sm,pill,circle}`、`font.{title,tiny,lineHeight,weightNormal,weightStrong,stack}`、
`layout.{content,controlTiny,controlSm,controlMd,controlLg,avatar,scrollbar,gridGap,gridGapLg,navItem}`、
`shadow.*`、`motion.*`。

---

## 5. 已声明的刻意偏离（不追求逐值相同）

| 项 | 本项目 | 参考站 | 理由 |
|---|---|---|---|
| `layout.tapMin` | 44px | 中号控件 34px | WCAG/移动端触控最小尺寸；仅**移动端交互控件**保留 44px，桌面端 GM 按钮已对齐 34px |
| `layout.maxWidth` | 560px | `html{min-width:1440px}`，内容列 1120px | 玩家端是手机竖屏单列；参考站的桌面栅格不适用 |
| `layout.sidebar` | none | 260px | 玩家端无侧栏（GM 端保留侧栏，宽 13rem） |
| `shadow.focusGlow` | 输入框柔光 | 2px outline | 项目自有交互反馈；焦点可见性已同时满足 `outline: 2px solid #ffbb70` |
| 字体分发 | 不分发 HarmonyOS 字体 | 自托管 `HarmonyOS_Sans_SC_Regular.ttf` | 交付包纪律：零外部依赖、无 CDN、不引入未授权字体；本机装有 HarmonyOS 时自动生效 |

---

## 6. 复现命令

```powershell
# 三端令牌一致性（唯一令牌源 → PC / WEB / 小程序）
cd "C:\Users\Administrator\Desktop\黑客松开发文档\TRPG-交付包-三件套\TRPG-服务端"
python scripts/check_ui_tokens.py

# 运行态实测（GM 端）
#   浏览器打开 http://192.168.10.110:9211/app ，控制台执行：
#   getComputedStyle(document.body).backgroundColor          -> rgb(16, 16, 20)
#   getComputedStyle(document.documentElement).getPropertyValue('--bg')  -> #101014

# 参考站实测（对照）
#   浏览器打开 https://www.cnmods.net/web/ ，控制台执行：
#   getComputedStyle(document.body).backgroundColor          -> rgb(16, 16, 20)
#   getComputedStyle(document.body).color                    -> rgba(255, 255, 255, 0.82)
#   getComputedStyle(document.body).fontFamily               -> HarmonyOS
#   getComputedStyle(document.querySelector('header')).backgroundColor -> rgb(38, 44, 49)
```
---

## 7. 与 captain 实测（`_r2_work/R32-REFERENCE-MODU.md`）的对账

captain 于 2026-09-27 独立实测了同一参考站。逐项对账结果：

| # | captain 实测 | 本任务复核（ego 通道，2026-09-27 05:4x） | 结论 |
|---|---|---|---|
| — | 页面底色 `#101014` | body 计算背景 `rgb(16,16,20)` | **一致** |
| R1 | 面板 `rgba(20,28,35,0.73)` + backdrop-blur，圆角 4px | `/web/moduleDetail` 面板 `bg-[#141c23ba] backdrop-blur rounded` → `rgba(20,28,35,0.73)` + `blur(8px)` + radius 4px + **border 0px** + **shadow none** | **一致**，并补测出"无边框、无阴影"与 padding `31px 23px` |
| R2 | 按钮透明底、圆角 3px、padding `0 10px` | `.n-button--default-type`（medium）：bg `rgba(0,0,0,0)`、**border 0px**（无 `.n-button__border` 子元素）、radius 3px、padding **`0 14px`**、高 34px、shadow none。`0 10px` 是 **small** 尺寸；medium 为 `0 14px` | **一致**；本项目按钮高度介于 medium(34) 与 large(40) 之间（移动端 44px 触控），故取 medium 的 `0 14px` |
| R3 | 输入框 `#212625`、圆角 3px | `.n-input` 280×34 bg `rgb(33,38,37)` radius 3px；`.n-input__border` 计算 `1px solid rgba(0,0,0,0)` | **一致**，并补测出"默认无可见边框" |
| R4 | （未列） | `.router-link-active` 计算：文字 `rgb(61,27,0)`，`background-image: url(nav_bg-*.png)`（金色贴图） | 新增发现：**激活导航 = 金底 + 墨色字** |
| R5 | 正文 `rgba(255,255,255,0.82)`、次级 `#b9b9b9` | 同 | **一致** |
| R6 | 字体 HarmonyOS + 系统回退、14px / 行高 1.6 | body `HarmonyOS`、14px、22.4px | **一致** |
| R7 | **无 box-shadow**，层次靠背景色差 + backdrop-blur | 8 个页面/视图扫描：带 `box-shadow` 的元素 **0 个**；`backdrop-filter` 仅出现在详情页面板 | **一致**（并给出可复现的扫描口径） |
| R8 | h3 `16px/700` | 模块卡 h3 = `16px/700`（`.font-bold`）；同时测到 `h2` `18px/600 #462500`、`h3` `18px/400 #623200` | **一致**；两种都存在，已同时收录（`font.weightStrong 600` + `font.weightBold 700`） |
| R9 | 导航项 80×40 居中 | `w-[80px] h-[40px] text-[16px]`，radius 0 | **一致**（`layout.navItem 40px`） |

### 据对账落地的 4 项修正（本轮已部署并运行态复测）

1. **面板**：新增 `color.cardTranslucent = rgba(20,28,35,0.73)` + `layout.blur = 8px`；PC/Web 的 `.card`、GM 的 `.panel` 改为半透明 + `backdrop-filter: blur(8px)`，**去掉边框与阴影**。
2. **次要按钮**：`.btn` 改为**全透明底 + 无边框**，padding `0 14px`（原为半透明底 + 1px 描边 + 16px 内边距）。
3. **输入框**：`.input` 默认边框改为 `1px solid transparent`（对齐 `.n-input__border` 实测值），聚焦才转强调色。
4. **导航激活态**：PC/Web 的 `.nav-btn[aria-current="true"]` 与 GM 的 `.sidebar-link-active` 改为**金底 `#ffbb70` + 墨色字 `#3d1b00`**（原为强调色文字 + 半透明底）。

新增令牌：`color.cardTranslucent`、`color.footerBg`、`font.weightBold`、`layout.blur`（三端一致，`CHECKED=88 MISMATCH=0`）。

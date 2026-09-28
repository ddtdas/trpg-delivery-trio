# Changelog

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.0.1] - 2026-09-26

### Added
- **服务端部署身份端点 `GET /__trpg_server__`**（additive，无鉴权）：返回
  `{service, ok, pid, port, deployment_id, install_dir, version}`，只暴露部署身份信息，
  不含任何密钥/令牌。用于把「端口上的是不是**本部署**」与「端口上是否**活着**」彻底分开。
- `run/deployment.id`：本部署的稳定身份（UUID v4，首次启动生成后每次复用；
  不可写时退化为部署根绝对路径的 SHA256 前 16 位）。
- `run/server.json` 新增 `deployment_id` 与 `install_dir` 两个字段（既有字段不变）。

### Fixed
- **服务端启动器用 `/api/health` 的「健康」代替「是本部署」做实例身份判定**，
  导致：显式指定被**别的 TRPG 部署 / 旧版服务端**占用的端口时**谎称幂等**（`exit 0`）
  并把本部署 `run/server.json` 覆写成**他人实例**的端口/PID；无参数自适应时也会
  **落回他人实例端口**。现改为以 `/__trpg_server__` 的 `install_dir`/`deployment_id` 判定：
  - 别的部署 / 旧版服务端占用显式端口 → **真冲突 `exit 2`** + 打印占用者 PID，且不覆写发现文件；
  - 无参数自适应 → **跳过**非本部署的占用者，落第一个**空闲**端口；
  - 本部署已在运行 → 幂等 `exit 0`（行为不变）。
- `stop.bat` 的「是否本部署」判定同样优先使用身份端点：不是本部署一律**拒绝停止**并 `exit 1`
  （命令行防误杀校验 `Test-IsServerProc` **保留**；端点不可达时退回该校验，**不放宽**守卫）。
- **F1：`install_dir` 判定分支在非 ASCII（中文）安装路径下失效**（PS 5.1）。
  `/__trpg_server__` 原以 `Content-Type: application/json`（**无 charset**）返回，按 HTTP/1.1
  历史默认，Windows PowerShell 5.1 的 `Invoke-WebRequest` 会按 **ISO-8859-1** 解码响应体 →
  `install_dir` 里的中文路径变乱码（并可能因解出 C1 控制字符而让 `ConvertFrom-Json` 直接失败）→
  「`install_dir` 相等」这条直接判据在中文路径下**恒为 False**，SPEC §三 2) 的并集退化为
  **仅 `deployment_id` 一支**；一旦 `run/deployment.id` 丢失/竞态，会把**本部署**误判为
  「别的部署」（`start` 假冲突 `exit 2` / `stop` 拒绝停止自家实例 `exit 1`）。两处互补修复：
  - **服务端**（`app/web/identity.py`）：`/__trpg_server__` 显式声明 `charset=utf-8`
    （仅影响本新增端点，属 additive）；
  - **PS 侧**（`scripts/start.ps1` / `scripts/stop.ps1`）：`Get-ServerIdentity` 新增
    `Get-ResponseTextUtf8`，**直接按 UTF-8 解码响应体原始字节**，不依赖服务端 header
    （对旧版/其它 JSON 响应一并免疫）。

### Notes
- **客户端无需改动**：`/__trpg_client__` 与自动发现行为保持不变，仅 `run/server.json` 多两个字段。
- `/api/health` 的响应**逐字节不变**（`{"status":"ok","version":...,"ts":...}`）。
- 冻结契约 6 项未触碰；既有 REST / `/access` 端点签名与行为零变化。
- **已知边界（交付仓）**：
  - 交付仓内**不含** `docs/contracts/`（冻结 6 项以**部署树**为比对根，非本仓）；
  - `tests/test_bw_schedule.py` 与 `tests/test_evolve.py` 依赖**未打包**的
    `scripts/sim` / `scripts/evolve`，在交付仓内需 `--ignore` 这两个模块
    （详见 README「开发与测试」，实测 576 passed / 0 failed）。

## [1.0.0] - 2026-09-25

### Added
- 首个定稿版本：TRPG 跑团辅助系统服务端（主持端）。
- FastAPI 应用（`app/`）：REST 接口、WebSocket 实时事件流（`/ws`）、主持端 UI 托管（`/app/`）、
  玩家端页面托管（`/player/`）。
- 领域内核（`trpg/`）：事件模型、规则内核、`agent/` 裁判与协调器，含冻结契约。
- 接入层（`app/web/access.py`）：三端 token（mobile / webapp / recorder）鉴权与连接码解析。
- 配置（`configs/`）：`access_config.yaml` 三端 token 与运行参数。
- 规则包（`rulepacks/`）、技能（`skills/`）、业务模块（`modules/`）。
- 主持端预构建 UI（`web/dist/`，挂载于 `/app/`）与零构建玩家端页面（`player-web/`，挂载于 `/player/`）。
- 自动化测试（`tests/`，pytest）。
- 启动脚本族：`start.bat` / `stop.bat`（纯 ASCII 包装器）+
  `scripts/start.ps1` / `scripts/stop.ps1`（真实逻辑，UTF-8 带 BOM）。
- **自适应端口**：默认从 9210 起，占用时依次探测 9210→9230；启动后落盘
  `run/server.port` 与 `run/server.json` 供客户端发现。
- 完整文档（`docs/`）：部署、运维、玩家端、小程序、跨端契约、验收报告、路线图、端点规格。

### Security
- `.gitignore` 排除运行期数据库、日志与本地配置，避免误提交 token 与事件数据。

[Unreleased]: https://example.com/trpg-server/compare/v1.0.1...HEAD
[1.0.1]: https://example.com/trpg-server/compare/v1.0.0...v1.0.1
[1.0.0]: https://example.com/trpg-server/releases/tag/v1.0.0

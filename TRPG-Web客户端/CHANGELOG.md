# Changelog

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.0.1] - 2026-09-26

### Notes
- **本端无代码改动**（纯说明性发布）。
- 服务端 v1.0.1 新增 **additive 身份端点** `GET /__trpg_server__`（无鉴权，返回
  `{service, ok, pid, port, deployment_id, install_dir, version}`），用于服务端
  `start.bat` / `stop.bat` 在同机装有**多个** TRPG 部署时区分「是不是本部署」
  （此前误用 `/api/health` 的「健康」当身份，会把别的部署/旧版服务端当成自己）。
- 服务端 `run/server.json` 新增 `deployment_id` 与 `install_dir` 两个字段。
  **本客户端只读其中的 `port` / `url`，多出的字段一律忽略 → 自动发现行为不变。**
- 客户端的 `GET /__trpg_client__` **保持不变**；客户端与本端点无交互。

## [1.0.0] - 2026-09-25

### Added
- 首个定稿版本：TRPG 跑团辅助系统客户端（PC / 移动浏览器玩家端）。
- `client/`：零构建、零 npm 依赖、无 CDN 外链的玩家端页面。
  - `index.html` —— 三视图骨架（连接设置 / 桌面 / 语音）。
  - `app.js` —— 全部前端逻辑：F1–F10、事件流、2s 轮询、可选 WS 增强、录音上传。
  - `app.css` —— 设计令牌（CSS 变量）+ 契约 §2 组件语义类名。
  - `strings.json` —— 固定文案表（三端逐字节一致，与小程序端 0 差异）。
  - `tokens.json` —— 设计令牌机器可读副本（逐值等于契约 §2）。
- 本地启动器：`start.bat` / `stop.bat`（纯 ASCII 包装器）+
  `scripts/start.ps1` / `scripts/stop.ps1`（真实逻辑，UTF-8 带 BOM）+
  `scripts/serve.py`（零依赖 Python 标准库静态服务器）。
- **自适应端口**：本地静态服务器默认从 8080 起，被占用则依次探测 8080→8090；
  启动后落盘 `run/client.port` 与 `run/client.json`。
- **服务端自动发现**：省略 `server-url` 时优先读取同机
  `../trpg-server/run/server.json`，读到即自动注入 `?server=` 并打开浏览器。
- 完整文档（`docs/PLAYER-WEB.md`）：页面功能、契约依据与部署说明。

### Notes
- 实现依据 `CROSS-END-CONTRACT.md` **v1.1**（冻结契约）。
- 契约 §4 中标注延期的两项功能，本端与小程序端一致地不实现。

[Unreleased]: https://example.com/trpg-client/compare/v1.0.1...HEAD
[1.0.1]: https://example.com/trpg-client/compare/v1.0.0...v1.0.1
[1.0.0]: https://example.com/trpg-client/releases/tag/v1.0.0

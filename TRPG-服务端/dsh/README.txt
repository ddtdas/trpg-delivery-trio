TRPG DSH 助手 说明
==================================================

本目录存放 DSH（DeepSeek Harness）助手相关的启动脚本。

【怎么用】
  双击  dsh\start.bat
  → 它会先确保 TRPG 服务端在运行（没起就自动起），
    然后用浏览器打开 DSH 助手面板（GM 界面的 #/dsh 路由）。

【DSH 助手是什么】
  它是随包交付的 DSH Web 前端静态产物，位于：
    ..\web\dist\keeper-ui\
  版本标识 rev = keeper-0.1.7-rc.1-static（68 个插件入口）。
  主持端（GM）界面把它嵌在「DSH 助手」页里。

【已知限制（如实说明）】
  1. 它是 DSH 的【前端外壳】，本身不含 DSH 引擎后端。
     因此页面能正常加载、不再报插件错误，但不会真正“连上”一个
     DSH 会话（会停在“重新连接中/选择工作区”）。
     要真正对话，需要另外提供 DSH 引擎 host。
  2. 需要先有服务端在跑（脚本会自动尝试拉起）。

【手动打开】
  http://127.0.0.1:<端口>/app/#/dsh
  <端口> 见 ..\run\server.port，或 start.bat 启动时打印的地址。
  注意：GM 端必须带 token，否则会一直显示“连接中断”：
  http://127.0.0.1:<端口>/app/?token=<webapp token>#/dsh
  token 见 ..\configs\access_config.yaml 里 webapp 项。
  （dsh\start.bat 会自动附加 token。）

【停止】
  DSH 助手是服务端的一部分，停止服务端即可：
  在服务端根目录双击 stop.bat。
【重要】DSH 面板的 token 是【另一个】参数
  URL 上的 ?token= 只管主界面的 WebSocket；
  DSH 面板自己从 localStorage 读 trpg_token。
  若面板提示“未配置接入 token”，在控制台执行（F12）：
    localStorage.setItem('trpg_token', '<webapp token>')
  token 见 ..\configs\access_config.yaml 的 webapp 项。设后无需重启。

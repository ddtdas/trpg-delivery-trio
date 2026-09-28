TRPG 模组包（.modpkg）存放目录
==================================================

本目录集中存放【预构建的模组包】，供参考与离线使用。

说明：
  1. 这些 .modpkg 是【样例产物】，不是运行时依赖。
  2. 服务端的下载端点 GET /api/modules/{id}/download
     会从 modules/{id}/ 【现场打包】生成一份确定性的 .modpkg，
     不从本目录读取。
  3. 重新构建：python scripts/_t5_build_deadlight.py
     其默认输出就是 modpacks/死光.modpkg。

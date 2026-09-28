// TD-2b/TD4: 构建后把 keeper-ui 静态产物拷入 web/dist/keeper-ui/（同源一体化托管）。
//
// 源: env KEEPER_UI_SRC（可选）|| <workspace>/trpg_agent/vendor/dsh-017-keeper/ui（新鲜 0.1.7-rc.1 组装物）
// 处理:
//   1) 递归复制全部静态文件（手动递归；本项目 node 下 fs.cpSync 崩溃已规避）;
//   2) 重写 index.html 根绝对引用为相对（同源子路径加载）;
//   3) TD4 方案 A: 复制 boot 插件集 client.js → dist/keeper-ui/plugins/@deepseek-ai/<pkg>/client.js
//      （源 = 平台已装 @deepseek-ai/dsh-client-* 包 lib/client.js，只读）;
//   4) TD4 方案 A: 把 keeper-ui-boot.js（__ModuleLoader__ facade + __DSH_BOOT__ 入口图）
//      作为 <head> 首脚本注入 index.html（消除 no-boot；provider 契约在引擎侧）。
// 铁律: 只写 web/dist 与读静态源/平台包（只读）；不引入 npm 依赖。
import { copyFileSync, mkdirSync, readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_SRC = resolve(webRoot, '../../../../trpg_agent/vendor/dsh-017-keeper/ui');
const BOOT_JS = resolve(webRoot, '../../../../trpg_agent/vendor/dsh-017-keeper/keeper-ui-boot.js');
const PNP_ROOT = 'E:\\dsh3080\\app\\node_modules\\.pnpm';
const src = process.env.KEEPER_UI_SRC ? resolve(process.env.KEEPER_UI_SRC) : DEFAULT_SRC;
const dest = join(webRoot, 'dist', 'keeper-ui');

/** boot 入口插件集（keeper-ui-boot.js 内 __DSH_BOOT__.entries 对应包）。 */
const BOOT_PLUGINS = [
  'dsh-client-modules', 'dsh-client-runtime', 'dsh-client-connection',
  'dsh-client-locale', 'dsh-client-ui-theme', 'dsh-client-ui-layout',
  'dsh-client-ui-renderer', 'dsh-client-ui-sidebar', 'dsh-client-ui-conversation',
  'dsh-client-ui-commands',
];

function copyTree(from, to) {
  mkdirSync(to, { recursive: true });
  let n = 0;
  for (const ent of readdirSync(from, { withFileTypes: true })) {
    const s = join(from, ent.name);
    const d = join(to, ent.name);
    if (ent.isDirectory()) n += copyTree(s, d);
    else if (ent.isFile()) { copyFileSync(s, d); n += 1; }
  }
  return n;
}

/** 定位 @deepseek-ai/<pkg> 的 lib/client.js：优先 0.1.7 新鲜插件暂存（plugins-fresh），
    回退平台已装包（只读）。TD4 版本适配：0.1.7 前端需 0.1.7 client 插件。 */
function pluginClientJs(pkg) {
  const fresh = join(resolve(webRoot, '../../../../trpg_agent/vendor/dsh-017-keeper/plugins-fresh'),
                     '@deepseek-ai', pkg, 'client.js');
  if (existsSync(fresh)) return fresh;
  let hits = [];
  try {
    hits = readdirSync(PNP_ROOT, { withFileTypes: true })
      .filter((e) => e.isDirectory() && e.name.startsWith('@deepseek-ai+dsh-'))
      .map((e) => join(PNP_ROOT, e.name, 'node_modules', '@deepseek-ai', pkg, 'lib', 'client.js'))
      .filter((p) => existsSync(p));
  } catch { hits = []; }
  return hits[0] || null;
}

mkdirSync(join(webRoot, 'dist'), { recursive: true });
const n = copyTree(src, dest);
console.log(`[copy-keeper-ui] copied ${n} files ${src} -> ${dest}`);

// TD4: boot 插件 client.js 静态拷贝
let copiedPlugins = 0;
for (const pkg of BOOT_PLUGINS) {
  const srcJs = pluginClientJs(pkg);
  if (!srcJs) { console.log(`[copy-keeper-ui] WARN plugin client.js missing: ${pkg}`); continue; }
  const out = join(dest, 'plugins', '@deepseek-ai', pkg, 'client.js');
  mkdirSync(dirname(out), { recursive: true });
  copyFileSync(srcJs, out);
  copiedPlugins += 1;
}
console.log(`[copy-keeper-ui] copied ${copiedPlugins}/${BOOT_PLUGINS.length} boot plugin client.js -> ${dest}/plugins/@deepseek-ai/...`);

// index.html: 相对引用重写
const idx = join(dest, 'index.html');
let html = readFileSync(idx, 'utf8');
const before = html;
html = html.replace(/(href|src)="\//g, '$1="./');
if (html !== before) writeFileSync(idx, html, 'utf8');

// TD4: __ModuleLoader__ facade + __DSH_BOOT__ 注入 + 种子 client 预加载（顺序：facade → 种子）
let bootJs = '';
try { bootJs = readFileSync(BOOT_JS, 'utf8'); } catch { console.log('[copy-keeper-ui] WARN keeper-ui-boot.js missing'); }
if (bootJs) {
  const seeds = '<script src="/app/keeper-ui/plugins/@deepseek-ai/dsh-client-modules/client.js"></script>\n'
    + '<script src="/app/keeper-ui/plugins/@deepseek-ai/dsh-client-runtime/client.js"></script>\n';
  if (html.includes('__ModuleLoader__')) {
    console.log('[copy-keeper-ui] boot already injected');
  } else {
    const tag = `<script>\n${bootJs}\n</script>\n${seeds}`;
    html = html.replace(/<head>/, `<head>\n${tag}`);
    writeFileSync(idx, html, 'utf8');
    console.log('[copy-keeper-ui] injected boot (facade + __DSH_BOOT__) + seed preloads into index.html <head>');
  }
}

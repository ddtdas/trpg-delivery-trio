// ensure-theme-order.mjs —— 构建后修正 R32 主题覆盖层的加载顺序（必须在 bundle CSS 之后）。
//
// 背景：web/index.html 源码里 theme-cnmods.css 的 <link> 写在 <head> 中，
// 而 vite build 会把入口 <script> / bundle CSS 追加到 <head> 末尾，
// 结果主题层反而排在 bundle CSS **之前** —— 同优先级下 bundle 覆盖主题，R32 失效。
// 本脚本把主题 <link>（连同其上方 R32 注释）移到 </head> 之前，使其最后加载。
//
// 幂等：已就位则不改动。仅写 web/dist/index.html。
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const idx = join(webRoot, 'dist', 'index.html');
const LINK = '<link rel="stylesheet" href="/app/assets/theme-cnmods.css">';

if (!existsSync(idx)) { console.log('[ensure-theme-order] dist/index.html absent, skip'); process.exit(0); }
let html = readFileSync(idx, 'utf8');
if (!html.includes(LINK)) { console.log('[ensure-theme-order] theme link absent, skip'); process.exit(0); }

const lines = html.split(/\r?\n/);
const linkIdx = lines.findIndex((l) => l.trim() === LINK);
if (linkIdx < 0) { console.log('[ensure-theme-order] link line not found, skip'); process.exit(0); }

const headEndIdx = lines.findIndex((l) => l.includes('</head>'));
if (headEndIdx < 0) { console.log('[ensure-theme-order] </head> not found, skip'); process.exit(0); }

// 已在 </head> 之前最后一行 → 幂等退出
const tail = lines.slice(linkIdx + 1, headEndIdx).filter((l) => l.trim() !== '');
if (tail.length === 0) { console.log('[ensure-theme-order] already last before </head>, no change'); process.exit(0); }

// 取出主题块（可选的上方 R32 注释 + link 行）
let start = linkIdx;
if (start - 1 >= 0 && /<!--/.test(lines[start - 1]) && /R32/.test(lines[start - 1])) start -= 1;
const block = lines.splice(start, linkIdx - start + 1);

// 重新插到 </head> 之前（headEndIdx 因 splice 前移）
const newHeadEnd = lines.findIndex((l) => l.includes('</head>'));
lines.splice(newHeadEnd, 0, ...block);

writeFileSync(idx, lines.join('\n'), 'utf8');
console.log('[ensure-theme-order] moved R32 theme link to last position before </head>');

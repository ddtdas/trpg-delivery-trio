// UI-R1 灰白黑主题清扫（web/src/components 其余文件的内联旧颜色 → 灰白黑令牌映射）。
// 只替换 class 字符串中的 Tailwind 旧色令牌；功能不动。可重复执行（幂等）。
import { readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const srcRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../src/components');
const skip = new Set(['ui.tsx', 'App.tsx']);

// 旧色 → 新色（顺序敏感：长 token 在前）
const MAP = [
  // 深底
  ['bg-slate-950/60', 'bg-gray-100'],
  ['bg-slate-950/70', 'bg-gray-100'],
  ['bg-slate-950', 'bg-gray-100'],
  ['bg-slate-900/80', 'bg-gray-50'],
  ['bg-slate-900/70', 'bg-white'],
  ['bg-slate-900/60', 'bg-gray-50'],
  ['bg-slate-900', 'bg-white'],
  ['bg-slate-800', 'bg-gray-800'],
  ['bg-slate-700/60', 'bg-gray-200'],
  // 文字灰
  ['text-slate-50', 'text-gray-900'],
  ['text-slate-100', 'text-gray-800'],
  ['text-slate-200', 'text-gray-700'],
  ['text-slate-300', 'text-gray-600'],
  ['text-slate-400', 'text-gray-500'],
  ['text-slate-500', 'text-gray-400'],
  ['text-slate-950', 'text-gray-900'],
  // 品牌黄 → 黑/灰
  ['text-amber-100', 'text-gray-900'],
  ['text-amber-200', 'text-gray-800'],
  ['text-amber-300', 'text-gray-700'],
  ['text-amber-400', 'text-gray-900'],
  ['bg-amber-500/10', 'bg-gray-100'],
  ['bg-amber-500', 'bg-gray-900'],
  ['bg-amber-400', 'bg-black'],
  ['hover:bg-amber-300', 'hover:bg-gray-800'],
  ['active:bg-amber-500', 'active:bg-gray-900'],
  ['border-amber-500/60', 'border-gray-300'],
  ['border-amber-500/50', 'border-gray-300'],
  ['border-amber-500/40', 'border-gray-300'],
  ['border-amber-500', 'border-gray-300'],
  ['border-amber-400', 'border-gray-400'],
  ['border-amber-300', 'border-gray-400'],
  ['focus-visible:outline-amber-300', 'focus-visible:outline-black'],
  ['focus-visible:ring-amber-400', 'focus-visible:ring-gray-400'],
  ['focus:border-amber-300', 'focus:border-gray-400'],
  ['accent-amber-500', 'accent-gray-900'],
  // 语义色 → 灰（成功/信息/装饰），红（错误）保留
  ['text-emerald-300', 'text-gray-800'],
  ['text-emerald-200', 'text-gray-800'],
  ['border-emerald-600', 'border-gray-400'],
  ['border-emerald-500', 'border-gray-400'],
  ['bg-emerald-500', 'bg-gray-700'],
  ['text-sky-300', 'text-gray-600'],
  ['text-sky-200', 'text-gray-600'],
  ['border-sky-600', 'border-gray-400'],
  ['bg-sky-500', 'bg-gray-600'],
  ['text-violet-300', 'text-gray-600'],
  ['border-violet-500', 'border-gray-400'],
  ['text-rose-300', 'text-red-400'],
  ['bg-rose-500', 'bg-red-600'],
];

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (name.endsWith('.tsx') && !skip.has(name)) out.push(p);
  }
  return out;
}

let changed = 0, total = 0;
for (const file of walk(srcRoot)) {
  let src = readFileSync(file, 'utf8');
  let cur = src;
  for (const [a, b] of MAP) cur = cur.split(a).join(b);
  if (cur !== src) { writeFileSync(file, cur, 'utf8'); changed += 1; }
  total += 1;
}
console.log(`[theme-sweep] mapped ${changed}/${total} component files (old theme tokens -> gray/white/black)`);
/** t40 对比度自查脚本（node 运行）：校验关键色对组合 ≥4.5:1，输出自查表。
 * 用法：node scripts/contrast-check.mjs（零依赖，WCAG 相对亮度公式）。
 * 颜色取自 src/index.css / 组件 panel 文字（深色主题实测值）。
 */
const pairs = [
  ['正文 slate-100 #f1f5f9 / 背景 #0b1220', '#f1f5f9', '#0b1220', 4.5],
  ['次级 slate-200 #e2e8f0 / 背景 #0b1220', '#e2e8f0', '#0b1220', 4.5],
  ['次级 slate-300 #cbd5e1 / 背景 #0b1220', '#cbd5e1', '#0b1220', 4.5],
  ['主按钮 amber-400 #fbbf24 / 字 slate-950 #020617', '#020617', '#fbbf24', 4.5],
  ['标题 amber-200 #fde68a / 背景 #0b1220', '#fde68a', '#0b1220', 4.5],
  ['危险 red-300 #fca5a5 / 背景 #0b1220', '#fca5a5', '#0b1220', 4.5],
  ['成功 emerald-300 #6ee7b7 / 背景 #0b1220', '#6ee7b7', '#0b1220', 4.5],
  ['面板字 slate-50 #f8fafc / 面板底 #0f172a', '#f8fafc', '#0f172a', 4.5],
  ['输入框字 slate-50 / 输入底 #020617', '#f8fafc', '#020617', 4.5],
  ['焦点环 amber-300 #fcd34d / 背景 #0b1220（非文本 3:1）', '#fcd34d', '#0b1220', 3.0],
];

function lum(hex) {
  const c = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((i) => {
    const v = parseInt(c.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

let fail = 0;
console.log('t40 对比度自查表（WCAG 常规文本 4.5:1 / 非文本 3:1）');
for (const [name, fg, bg, bar] of pairs) {
  const r = ratio(fg, bg);
  const ok = r >= bar;
  if (!ok) fail += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${r.toFixed(2)}:1 (≥${bar}) ${name}`);
}
if (fail > 0) {
  console.error(`CONTRAST_FAIL: ${fail} 对组合未达标`);
  process.exit(1);
}
console.log('CONTRAST_OK: 全部达标');

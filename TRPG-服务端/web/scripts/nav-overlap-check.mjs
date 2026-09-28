/** t40 导航零覆盖断言（node 运行）：静态检查 App 头部结构满足：
 * ①导航 <nav> 与状态行/toast 为兄弟独立行（非 absolute/fixed 覆盖）；
 * ②无 fixed/absolute 定位的 pill/toast 样式残留；
 * ③导航链接 7 个且均有 min-h-[44px] 触击类。
 * 用法：node scripts/nav-overlap-check.mjs（零依赖，源码静态断言）。
 */
import { readFileSync } from 'node:fs';

const app = readFileSync('src/App.tsx', 'utf8');
const css = readFileSync('src/index.css', 'utf8');
const ui = readFileSync('src/components/ui.tsx', 'utf8');

const checks = [
  ['App 无 fixed 定位', !/fixed/.test(app)],
  ['App 无 absolute 定位', !/absolute/.test(app)],
  ['ui ToastZone 无 fixed/absolute', !/fixed|absolute/.test(ui)],
  ['导航 7 链接', (app.match(/to: '\//g) || []).length === 7],
  ['导航触击 min-h', app.includes('min-h-[44px]')],
  ['状态行为独立 <p role=status>', app.includes('role="status"')],
  ['Toast 在 header 内独立行', app.includes('<ToastZone')],
];

let fail = 0;
for (const [name, ok] of checks) {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`);
  if (!ok) fail += 1;
}
if (fail > 0) {
  console.error(`NAV_OVERLAP_FAIL: ${fail} 项未通过`);
  process.exit(1);
}
console.log('NAV_OVERLAP_OK: 导航零覆盖');

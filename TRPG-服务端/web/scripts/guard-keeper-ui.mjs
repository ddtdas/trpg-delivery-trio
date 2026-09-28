// R2 fail-safe guard: run BEFORE `vite build`.
//
// Why: web/dist/keeper-ui/ (~158 files) is produced from a vendor source that
// lives OUTSIDE the delivery package. `vite build` uses emptyOutDir, so it
// wipes dist first - including keeper-ui. copy-keeper-ui.mjs runs AFTER vite
// and reads that missing source, so it cannot restore it: running `npm run
// build` inside the delivered package would destroy keeper-ui permanently.
//
// This guard runs first and fails fast, so vite never touches dist when the
// source is unavailable.
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_SRC = resolve(webRoot, '../../../../trpg_agent/vendor/dsh-017-keeper/ui');
const src = process.env.KEEPER_UI_SRC ? resolve(process.env.KEEPER_UI_SRC) : DEFAULT_SRC;
const dest = join(webRoot, 'dist', 'keeper-ui');

if (!existsSync(src)) {
  console.error('');
  console.error('======================================================================');
  console.error('GUARD: keeper-ui source NOT found - build aborted before vite ran.');
  console.error('======================================================================');
  console.error('  expected src         : ' + src);
  console.error('  existing dist/keeper-ui: ' + (existsSync(dest) ? 'PRESENT (preserved)' : 'ABSENT'));
  console.error('');
  console.error('  The source is NOT shipped in the delivery package (only the built');
  console.error('  web/dist/keeper-ui is). `vite build` empties dist, and');
  console.error('  copy-keeper-ui.mjs runs after vite and reads that missing source,');
  console.error('  so keeper-ui would be deleted and could NOT be restored.');
  console.error('');
  console.error('  Main bundle only      -> npm run build:remote   (does not touch keeper-ui)');
  console.error('  Rebuild keeper-ui too -> set KEEPER_UI_SRC to the dsh-017-keeper/ui dir');
  console.error('');
  process.exit(1);
}
console.log('GUARD: keeper-ui source found: ' + src);
process.exit(0);

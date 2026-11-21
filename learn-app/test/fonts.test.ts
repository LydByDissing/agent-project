// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.16 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_spa]
//   [intent]Proves the built SPA is self-contained: no outside URLs in sources or dist, and every declared font file is shipped as woff2 with its license.[/intent]
// [/origin]
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { tmp as tmpDir } from './helpers/tmp.js';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';

const APP = resolve(dirname(fileURLToPath(import.meta.url)), '..');
let dist = '';

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));
}

beforeAll(() => {
  // build into a tmp dir so the test checks current sources without touching the committed dist/
  dist = tmpDir('learn-fonts-dist-');
  execFileSync('npx', ['vite', 'build', '--outDir', dist, '--emptyOutDir'], { cwd: APP, stdio: 'pipe' });
}, 120_000);

describe('bundled fonts', () => {
  it('has no Google Fonts or other external font URLs in src/spa or the built output', () => {
    for (const file of [...walk(join(APP, 'src', 'spa')), ...walk(dist)]) {
      if (/\.woff2?$/.test(file)) continue;
      const text = readFileSync(file, 'utf8');
      expect(text, file).not.toMatch(/googleapis|gstatic/i);
      if (/\.(css|html)$/.test(file)) expect(text, file).not.toMatch(/(src|href)\s*=\s*"https?:|url\(\s*["']?https?:/i);
    }
  });

  it('ships the 7 woff2 faces referenced by the built CSS', () => {
    const css = walk(join(dist, 'assets')).filter((f) => f.endsWith('.css')).map((f) => readFileSync(f, 'utf8')).join('\n');
    const faces = [...css.matchAll(/font-family:"?([^";}]+)"?;font-style:normal;font-weight:(\d+)[^}]*url\(([^)]+\.woff2)\)/g)];
    expect(faces.map((m) => `${m[1]} ${m[2]}`).sort()).toEqual(
      ['IBM Plex Mono 400', 'IBM Plex Mono 500', 'IBM Plex Sans 400', 'IBM Plex Sans 500', 'IBM Plex Sans 600', 'Source Serif 4 400', 'Source Serif 4 600'].sort(),
    );
    for (const m of faces) {
      const file = join(dist, 'assets', m[3].replace(/^\.?\/?(assets\/)?/, ''));
      expect(existsSync(file), file).toBe(true);
      expect(readFileSync(file).subarray(0, 4).toString('latin1')).toBe('wOF2');
    }
  });

  it('includes the OFL license text', () => {
    expect(readFileSync(join(APP, 'fonts-LICENSE.txt'), 'utf8')).toMatch(/SIL OPEN FONT LICENSE Version 1\.1/);
  });

  it('the committed dist/ also has no external font URLs', () => {
    for (const file of walk(join(APP, 'dist')).filter((f) => !/\.woff2?$/.test(f))) expect(readFileSync(file, 'utf8'), file).not.toMatch(/googleapis|gstatic/i);
  });
});

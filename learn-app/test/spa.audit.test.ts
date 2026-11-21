// [origin ref=llm-dsl-gu1y.6 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_spa]
//   [intent]Checks the built SPA against the t3 acceptance criterion: the bundle polls every 2s with the wave-finished banner, and a headless Chromium render of the real server shows job pills, the lesson heading and the what-changed note.[/intent]
// [/origin]
import { execFile, spawn, type ChildProcess } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { homedir, tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const execFileAsync = promisify(execFile);
const LEARN_APP = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = resolve(LEARN_APP, '..');
const CHROMIUM = '/snap/bin/chromium';
const SNAP_COMMON = join(homedir(), 'snap', 'chromium', 'common');
const canRunChromium = existsSync(CHROMIUM) && existsSync(SNAP_COMMON);
const tmp = (): string => mkdtempSync(join(tmpdir(), 'learn-spa-audit-'));

const NOW_RUNNING = {
  run: 'r1',
  wave: 1,
  jobs: [
    { id: 't1', title: 'Cache headers', topics: ['backend/http-caching'], status: 'running' },
    { id: 't4', title: 'Grid layout', topics: ['frontend/css-grid'], status: 'running' },
  ],
};

async function freePort(): Promise<number> {
  return new Promise((res) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => {
      const p = (s.address() as { port: number }).port;
      s.close(() => res(p));
    });
  });
}

describe('built SPA bundle', () => {
  const dist = join(LEARN_APP, 'dist');
  const bundle = (): string => {
    const js = readdirSync(join(dist, 'assets')).find((f) => f.endsWith('.js'));
    if (!js) throw new Error('no JS bundle in dist/assets');
    return readFileSync(join(dist, 'assets', js), 'utf8');
  };

  it('dist/index.html loads a module script from ./assets', () => {
    const html = readFileSync(join(dist, 'index.html'), 'utf8');
    expect(html).toMatch(/<script type="module"[^>]*src="\.\/assets\/index-[^"]+\.js"/);
  });

  it('bundle polls /api/now on a 2000 ms interval', () => {
    // esbuild/vite minify 2000 to 2e3; the positive control is the setInterval call itself
    expect(bundle()).toMatch(/setInterval\(\(\)=>void \w+\(\),2e3\)/);
  });

  it('bundle contains the wave-finished banner text', () => {
    expect(bundle()).toContain('finished. Agents are waiting for you in the terminal.');
  });
});

describe.skipIf(!canRunChromium)('headless Chromium render of the real server', () => {
  let child: ChildProcess | undefined;
  let base = '';
  let project = '';
  let home = '';
  let userData = '';

  const startServer = async (now: unknown): Promise<void> => {
    child?.kill();
    project = tmp();
    home = tmp();
    mkdirSync(home, { recursive: true });
    cpSync(join(REPO, 'learn'), join(project, 'learn'), { recursive: true, preserveTimestamps: true });
    mkdirSync(join(project, '.sdd'));
    writeFileSync(join(project, '.sdd', 'now.json'), JSON.stringify(now));
    writeFileSync(
      join(home, 'learner.json'),
      JSON.stringify({ schema: 1, interest: { backend: 'deep', frontend: 'skip' }, mastery: {}, history: [] }),
    );
    const port = await freePort();
    base = `http://127.0.0.1:${port}`;
    child = spawn(process.execPath, [join(LEARN_APP, 'server.js'), '--project', project], {
      env: { ...process.env, SDD_LEARN_HOME: home, SDD_LEARN_PORT: String(port) },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    await new Promise<void>((res, rej) => {
      child!.stdout!.on('data', (d: Buffer) => d.toString().includes('listening') && res());
      child!.on('exit', (c) => rej(new Error(`server exited ${c}`)));
      setTimeout(() => rej(new Error('server start timeout')), 10_000);
    });
  };

  const dumpDom = async (): Promise<string> => {
    const { stdout } = await execFileAsync(
      CHROMIUM,
      ['--headless', '--no-sandbox', '--disable-gpu', `--user-data-dir=${userData}`, '--virtual-time-budget=5000', '--dump-dom', `${base}/`],
      { timeout: 60_000, maxBuffer: 16 * 1024 * 1024 },
    );
    return stdout;
  };

  beforeAll(() => {
    userData = mkdtempSync(join(SNAP_COMMON, 'learn-spa-ud-'));
  });

  afterAll(() => {
    child?.kill();
    if (userData) rmSync(userData, { recursive: true, force: true });
  });

  it('shows the job pills, the lesson heading and the what-changed note for a running wave', async () => {
    await startServer(NOW_RUNNING);
    const dom = await dumpDom();

    expect(dom).toContain('<span class="t">t1 Cache headers</span>');
    expect(dom).toContain('<span class="t">t4 Grid layout</span>');
    expect(dom).toContain('<h1>Freshness and Cache-Control</h1>');
    expect(dom).toContain('What changed in topics you skip');
    expect(dom).toContain('frontend/css-grid: Grid layout (t4, running)');
    expect(dom).toMatch(/<div class="banner" id="banner" hidden/);
  }, 90_000);

  it('shows the wave-finished banner once every job is done', async () => {
    await startServer({ ...NOW_RUNNING, jobs: NOW_RUNNING.jobs.map((j) => ({ ...j, status: 'done' })) });
    const dom = await dumpDom();

    expect(dom).toMatch(/<div class="banner" id="banner">/);
    expect(dom).toContain('Wave 1 finished. Agents are waiting for you in the terminal.');
  }, 90_000);
});

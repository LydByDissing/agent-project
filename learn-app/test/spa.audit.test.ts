// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.6 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_spa]
//   [intent]Checks the built SPA against the t3 acceptance criterion: the bundle polls every 2s with the wave-finished banner, and a headless Chromium render of the real server shows job pills, the lesson heading and the what-changed note.[/intent]
// [/origin]
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { canRunChromium, launchPage } from './helpers/browser.js';
import { LEARN_APP, makeProject, startLearnServer } from './helpers/server.js';

const LEARNER = { schema: 1, interest: { backend: 'deep', frontend: 'skip' }, mastery: {}, history: [] };

const NOW_RUNNING = {
  run: 'r1',
  wave: 1,
  jobs: [
    { id: 't1', title: 'Cache headers', topics: ['backend/http-caching'], status: 'running' },
    { id: 't4', title: 'Grid layout', topics: ['frontend/css-grid'], status: 'running' },
  ],
};

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
    expect(bundle()).toMatch(/setInterval\(\(\)=>void [\w$]+\(\),2e3\)/);
  });

  it('bundle contains the wave-finished banner text', () => {
    expect(bundle()).toContain('finished. Agents are waiting for you in the terminal.');
  });
});

describe.skipIf(!canRunChromium)('headless Chromium render of the real server', () => {
  /** Serves a fresh project with the given now.json and returns the page DOM once the wave strip and lesson have rendered. */
  const renderDom = async (now: unknown): Promise<string> => {
    const { project, home } = makeProject({ now, learner: LEARNER });
    const srv = await startLearnServer({ project, home });
    const page = await launchPage(`${srv.base}/`);
    await page.waitFor(`document.querySelector('#wave .job') && document.querySelector('article.lesson h1')`, 'wave strip and lesson heading');
    return page.evaluate<string>('document.documentElement.outerHTML');
  };

  it('shows the job pills, the lesson heading and the what-changed note for a running wave', async () => {
    const dom = await renderDom(NOW_RUNNING);

    expect(dom).toContain('<span class="t">t1 Cache headers</span>');
    expect(dom).toContain('<span class="t">t4 Grid layout</span>');
    expect(dom).toContain('<h1>Freshness and Cache-Control</h1>');
    expect(dom).toContain('What changed in topics you skip');
    expect(dom).toContain('frontend/css-grid: Grid layout (t4, running)');
    expect(dom).toMatch(/<div class="banner" id="banner" hidden/);
  }, 90_000);

  it('shows the wave-finished banner once every job is done', async () => {
    const dom = await renderDom({ ...NOW_RUNNING, jobs: NOW_RUNNING.jobs.map((j) => ({ ...j, status: 'done' })) });

    expect(dom).toMatch(/<div class="banner" id="banner">/);
    expect(dom).toContain('Wave 1 finished. Agents are waiting for you in the terminal.');
  }, 90_000);
});

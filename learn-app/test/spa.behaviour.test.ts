// [origin ref=llm-dsl-gu1y.17 req=REQ-OPERATOR-EDU-002,REQ-OPERATOR-EDU-003,REQ-OPERATOR-EDU-010,REQ-OPERATOR-EDU-011 c4=learn_app/learn_spa]
//   [intent]Drives the real server in headless Chromium to prove the SPA's live behaviour: the wave strip follows now.json within 5 s, a failed quiz shows Retry and retrying recovers, Sources render as links and path refs, and the diagram zoom buttons change scale.[/intent]
// [/origin]
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { canRunChromium, launchPage } from './helpers/browser.js';
import { makeProject, sleep, startLearnServer } from './helpers/server.js';
import { tmp } from './helpers/tmp.js';

const LEARNER = { schema: 1, interest: { backend: 'deep' }, mastery: {}, history: [] };
const job = (id: string, title: string, status: string) => ({ id, title, topics: ['backend/http-caching'], status });

describe.skipIf(!canRunChromium)('SPA behaviour in headless Chromium', () => {
  it('wave strip flips from running to done and shows the finished banner within 5 s of now.json changing', async () => {
    const running = { run: 'r1', wave: 1, jobs: [job('t1', 'Cache headers', 'running'), job('t2', 'ETag support', 'running')] };
    const { project, home } = makeProject({ now: running, learner: LEARNER });
    const srv = await startLearnServer({ project, home });
    const page = await launchPage(`${srv.base}/`);

    await page.waitFor(`document.querySelectorAll('#wave .job[data-s="running"]').length === 2`, 'two running job pills');
    expect(await page.evaluate<boolean>(`document.getElementById('banner').hidden`), 'banner must be hidden while jobs run').toBe(true);
    expect(await page.evaluate<string>(`document.querySelector('#wave .label').textContent`)).toBe('Wave 1 · 0/2 done');

    writeFileSync(join(project, '.sdd', 'now.json'), JSON.stringify({ ...running, jobs: running.jobs.map((j) => ({ ...j, status: 'done' })) }));
    const changedAt = Date.now();
    await page.waitFor(
      `document.querySelectorAll('#wave .job[data-s="done"]').length === 2 && !document.getElementById('banner').hidden`,
      'both pills done and the banner visible',
      5000,
    );
    expect(Date.now() - changedAt).toBeLessThanOrEqual(5500);
    expect(await page.evaluate<string>(`document.getElementById('banner-text').textContent`)).toBe('Wave 1 finished. Agents are waiting for you in the terminal.');
    expect(await page.evaluate<string>(`document.querySelector('#wave .label').textContent`)).toBe('Wave 1 · 2/2 done');
  }, 60_000);

  it('a failed quiz shows the error with Retry, every Retry click re-requests the quiz, and a valid response shows the questions', async () => {
    const dir = tmp('learn-quiz-mode-');
    const modeFile = join(dir, 'mode');
    const log = join(dir, 'argv.log');
    writeFileSync(modeFile, 'exit');
    const { project, home } = makeProject({ now: { jobs: [] }, learner: LEARNER });
    const srv = await startLearnServer({ project, home, env: { FAKE_CLAUDE_MODE_FILE: modeFile, FAKE_CLAUDE_LOG: log } });
    const calls = (): number => {
      try {
        return readFileSync(log, 'utf8').split('\n').filter(Boolean).length;
      } catch {
        return 0;
      }
    };
    const page = await launchPage(`${srv.base}/#lesson/backend/http-caching/01-freshness`);

    await page.waitFor(`document.querySelector('#qs #retry')`, 'Retry button after the first failure');
    const errorText = await page.evaluate<string>(`document.querySelector('#qs .result.bad').textContent`);
    expect(errorText).toContain('ClaudeExitError');
    expect(errorText).toContain('boom: not logged in');
    expect(errorText).toContain('Retry');
    expect(await page.evaluate<number>(`document.querySelectorAll('#qs .q').length`)).toBe(0);
    expect(calls()).toBe(1);

    // Retry while still broken: a second request is made and the error remains.
    await page.evaluate(`document.getElementById('retry').click()`);
    for (let i = 0; i < 100 && calls() < 2; i++) await sleep(100);
    expect(calls()).toBe(2);
    await page.waitFor(`document.querySelector('#qs #retry') && document.getElementById('gen').textContent.includes('error')`, 'error state again');

    // Fix the CLI, retry: the questions appear.
    writeFileSync(modeFile, 'valid');
    await page.evaluate(`document.getElementById('retry').click()`);
    await page.waitFor(`document.querySelectorAll('#qs .q').length === 3`, 'three questions after a successful retry');
    expect(calls()).toBe(3);
    expect(await page.evaluate<number>(`document.querySelectorAll('#qs #retry').length`)).toBe(0);
    expect(await page.evaluate<string>(`document.querySelector('#qs .q h3').textContent`)).toContain('Question 1 about the lesson?');
  }, 90_000);

  it('Sources: url sources are links that open safely, path sources are shown as path:line text', async () => {
    const { project, home } = makeProject({ now: { jobs: [] }, learner: LEARNER });
    const dir = join(project, 'learn', 'backend', 'refs');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'index.yaml'), 'title: Refs\nsummary: Source rendering.\n');
    writeFileSync(
      join(dir, '01-sources.md'),
      [
        '---',
        'id: backend/refs/01-sources',
        'title: Source kinds',
        'level: intro',
        'requires: []',
        'sources:',
        '  - title: "RFC 9111 Caching"',
        '    url: https://www.rfc-editor.org/rfc/rfc9111',
        '  - title: "Cache middleware"',
        '    path: learn-app/src/server/app.ts',
        '    line: 42',
        'updated: 2026-11-21',
        '---',
        '',
        'Body text.',
        '',
      ].join('\n'),
    );
    const srv = await startLearnServer({ project, home });
    const page = await launchPage(`${srv.base}/#lesson/backend/refs/01-sources`);
    await page.waitFor(`document.querySelectorAll('.sources li').length === 2`, 'two source rows');

    const rows = await page.evaluate<Array<{ text: string; href: string | null; target: string | null; rel: string | null; kind: string }>>(
      `[...document.querySelectorAll('.sources li')].map((li) => { const a = li.querySelector('a'); return { text: li.textContent, href: a && a.getAttribute('href'), target: a && a.getAttribute('target'), rel: a && a.getAttribute('rel'), kind: li.querySelector('.k').textContent }; })`,
    );
    expect(rows[0]).toEqual({ text: 'RFC 9111 Cachinglink', href: 'https://www.rfc-editor.org/rfc/rfc9111', target: '_blank', rel: 'noopener', kind: 'link' });
    expect(rows[1].href, 'a path source must not be a link').toBeNull();
    expect(rows[1].text).toBe('Cache middleware learn-app/src/server/app.ts:42this repo');
    expect(rows[1].kind).toBe('this repo');

    // The seed lesson renders all four of its url sources as links.
    const seed = await launchPage(`${srv.base}/#lesson/backend/http-caching/01-freshness`);
    await seed.waitFor(`document.querySelectorAll('.sources li').length === 4`, 'four seed sources');
    expect(await seed.evaluate<number>(`document.querySelectorAll('.sources li a[href^="https://"]').length`)).toBe(4);
  }, 90_000);

  it('SVG zoom: + raises the diagram scale in 0.25 steps, - lowers it, and it never drops below 1', async () => {
    const { project, home } = makeProject({ now: { jobs: [] }, learner: LEARNER });
    const srv = await startLearnServer({ project, home });
    const page = await launchPage(`${srv.base}/#lesson/backend/http-caching/02-revalidation`);
    await page.waitFor(`document.querySelector('figure.dia .dia-view img')`, 'wrapped diagram');
    const transform = (): Promise<string> => page.evaluate<string>(`document.querySelector('figure.dia img').style.transform`);
    const press = (dir: 1 | -1): Promise<unknown> => page.evaluate(`document.querySelector('figure.dia button[data-z="${dir}"]').click()`);

    expect(await transform(), 'no zoom applied before any click').toBe('');
    await press(1);
    expect(await transform()).toBe('scale(1.25)');
    await press(1);
    expect(await transform()).toBe('scale(1.5)');
    await press(-1);
    expect(await transform()).toBe('scale(1.25)');
    await press(-1);
    await press(-1);
    expect(await transform()).toBe('scale(1)');
  }, 90_000);
});

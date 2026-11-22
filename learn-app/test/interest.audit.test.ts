// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.10,llm-dsl-2zv1.18 req=REQ-OPERATOR-EDU-006 c4=learn_app/learn_spa]
//   [intent]Audits the interest feature against REQ-OPERATOR-EDU-006: PUT /api/interest is atomic over partial maps, domain and topic skip semantics hold in selection, GET titles come from index.yaml, and the onboarding and lesson controls write the right keys when clicked in a real headless Chromium.[/intent]
// [/origin]
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { parse } from 'yaml';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { makeApp } from './helpers/app.js';
import { canRunChromium, closeAllPages, launchPage } from './helpers/browser.js';
import { FAKE, REPO, makeProject, sleep, startLearnServer } from './helpers/server.js';
import { tmp as tmpDir } from './helpers/tmp.js';

const tmp = (): string => tmpDir('learn-interest-audit-');

type Learner = { schema: 1; interest: Record<string, string>; mastery: object; history: unknown[] };
const L = (interest: Record<string, string>): Learner => ({ schema: 1, interest, mastery: {}, history: [] });

let savedEnv: Record<string, string | undefined> = {};
beforeAll(() => {
  savedEnv = { SDD_LEARN_HOME: process.env.SDD_LEARN_HOME, SDD_LEARN_CLAUDE: process.env.SDD_LEARN_CLAUDE };
  process.env.SDD_LEARN_HOME = tmp();
  process.env.SDD_LEARN_CLAUDE = FAKE;
});
afterAll(() => {
  for (const [k, v] of Object.entries(savedEnv)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
});

function fixture(learner?: Learner) {
  const { project, home } = makeProject({ tls: true, learner, domains: ['backend'] });
  const app = makeApp({
    project,
    distDir: project,
    home,
    today: () => '2026-11-21',
    claude: () => ({ bin: FAKE, timeoutMs: 10_000 }),
  });
  const put = (body: unknown, raw?: string) =>
    app.request('/api/interest', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: raw ?? JSON.stringify(body) });
  const learnerFile = join(home, 'learner.json');
  const readInterest = (): Record<string, string> => (JSON.parse(readFileSync(learnerFile, 'utf8')) as Learner).interest;
  const next = async () => (await (await app.request('/api/next')).json()) as { lesson: { id: string; level: string; topic: string; domain: string } | null };
  const tree = async () =>
    (await (await app.request('/api/tree')).json()) as {
      domains: Array<{ id: string; interest: string; topics: Array<{ id: string; interest: string; lessons: Array<{ id: string; status: string }> }> }>;
    };
  return { project, home, app, put, learnerFile, readInterest, next, tree };
}

describe('PUT /api/interest is atomic over a partial map', () => {
  it('a valid topic entry before an invalid value writes neither and creates no learner.json', async () => {
    const f = fixture();
    const res = await f.put({ 'backend/tls-basics': 'deep', 'backend/http-caching': 'never' });
    const body = (await res.json()) as { error: string; key: string };
    expect(res.status).toBe(400);
    expect(body.error).toBe('bad_value');
    expect(body.key).toBe('backend/http-caching');
    expect(existsSync(f.learnerFile), 'learner.json must not be created by a rejected PUT').toBe(false);
  });

  it('a valid entry before an unknown key leaves an existing learner.json byte-identical', async () => {
    const f = fixture(L({ backend: 'basics' }));
    const before = readFileSync(f.learnerFile, 'utf8');
    const res = await f.put({ backend: 'deep', 'backend/nope': 'skip' });
    const body = (await res.json()) as { error: string; key: string };
    expect(res.status).toBe(400);
    expect(body.error).toBe('unknown_key');
    expect(body.key).toBe('backend/nope');
    expect(readFileSync(f.learnerFile, 'utf8')).toBe(before);
  });

  it('a bad entry before a valid entry writes neither, so the valid topic key is absent from learner.json', async () => {
    const f = fixture(L({ backend: 'basics' }));
    const res = await f.put({ 'backend/http-caching': 'never', 'backend/tls-basics': 'deep' });
    expect(res.status).toBe(400);
    expect(f.readInterest()).toEqual({ backend: 'basics' });
  });
});

describe('GET /api/interest titles come from index.yaml', () => {
  it('domain and topic titles equal the title fields of the learn/ index.yaml files', async () => {
    const f = fixture();
    const body = (await (await f.app.request('/api/interest')).json()) as {
      domains: Array<{ id: string; title: string; topics: Array<{ id: string; title: string }> }>;
    };
    const domainYaml = parse(readFileSync(join(REPO, 'learn', 'backend', 'index.yaml'), 'utf8')) as { title: string };
    const topicYaml = parse(readFileSync(join(REPO, 'learn', 'backend', 'http-caching', 'index.yaml'), 'utf8')) as { title: string };
    const domain = body.domains.find((d) => d.id === 'backend')!;
    expect(domain.title).toBe(domainYaml.title);
    expect(domain.topics.find((t) => t.id === 'backend/http-caching')!.title).toBe(topicYaml.title);
    expect(domain.topics.find((t) => t.id === 'backend/tls-basics')!.title).toBe('TLS basics');
  });

  it('editing a domain title in learn/backend/index.yaml is reflected by the next GET', async () => {
    const f = fixture();
    const file = join(f.project, 'learn', 'backend', 'index.yaml');
    writeFileSync(file, readFileSync(file, 'utf8').replace(/^title:.*$/m, 'title: Renamed Backend'));
    const body = (await (await f.app.request('/api/interest')).json()) as { domains: Array<{ title: string }> };
    expect(body.domains[0].title).toBe('Renamed Backend');
  });
});

describe('domain-level skip in lesson selection', () => {
  it('domain skip with no topic override returns no lesson from any of its topics', async () => {
    const f = fixture(L({ backend: 'skip' }));
    const body = await f.next();
    expect(body.lesson, `expected no lesson, got ${body.lesson?.id}`).toBeNull();
  });

  it('domain skip with a topic set to basics returns only an intro lesson of that topic', async () => {
    const f = fixture(L({ backend: 'skip', 'backend/http-caching': 'basics' }));
    const body = await f.next();
    expect(body.lesson).not.toBeNull();
    expect(body.lesson!.id.startsWith('backend/http-caching/')).toBe(true);
    expect(body.lesson!.level).toBe('intro');
  });

  it('domain skip with a topic set to basics marks the sibling topic as skipped in the tree', async () => {
    const f = fixture(L({ backend: 'skip', 'backend/http-caching': 'basics' }));
    const t = await f.tree();
    expect(t.domains[0].interest).toBe('skip');
    const tls = t.domains[0].topics.find((x) => x.id === 'backend/tls-basics')!;
    expect(tls.interest).toBe('skip');
    expect(tls.lessons.every((l) => l.status === 'skipped')).toBe(true);
  });

  it('domain skip set by PUT then topic deep set by PUT brings that topic back into selection', async () => {
    const f = fixture(L({ backend: 'deep' }));
    expect((await f.put({ key: 'backend', value: 'skip' })).status).toBe(200);
    expect((await f.next()).lesson).toBeNull();
    expect((await f.put({ key: 'backend/http-caching', value: 'deep' })).status).toBe(200);
    expect((await f.next()).lesson?.id.startsWith('backend/http-caching/')).toBe(true);
  });
});

describe.skipIf(!canRunChromium)('browser: interest controls drive the real server', () => {
  afterEach(closeAllPages);

  async function waitUntil(check: () => boolean, label: string, ms = 20_000): Promise<void> {
    const end = Date.now() + ms;
    while (!check()) {
      if (Date.now() > end) throw new Error(`timed out waiting for ${label}`);
      await sleep(100);
    }
  }

  async function startServer(learner: Learner | null) {
    const { project, home } = makeProject({ tls: true, now: { jobs: [] }, learner });
    const srv = await startLearnServer({ project, home });
    const learnerFile = join(home, 'learner.json');
    const readInterest = (): Record<string, string> =>
      existsSync(learnerFile) ? (JSON.parse(readFileSync(learnerFile, 'utf8')) as Learner).interest : {};
    return { base: srv.base, learnerFile, readInterest, getJson: async <T,>(path: string) => (await fetch(srv.base + path)).json() as Promise<T> };
  }

  it('onboarding: choosing deep on the backend domain writes the domain key only', async () => {
    const s = await startServer(null);
    const page = await launchPage(`${s.base}/`);
    await page.waitFor(`document.querySelector('[data-k="backend"][data-v="deep"]')`, 'onboarding deep button for backend');
    await page.evaluate(`document.querySelector('[data-k="backend"][data-v="deep"]').click()`);
    await waitUntil(() => s.readInterest().backend === 'deep', 'learner.json backend=deep');
    expect(s.readInterest()).toEqual({ backend: 'deep' });
  }, 120_000);

  it('"Not for me" on a lesson writes the topic key skip, not the domain key, and shows the next lesson', async () => {
    const s = await startServer(L({ backend: 'deep' }));
    const first = await s.getJson<{ lesson: { id: string; title: string } }>('/api/next');
    expect(first.lesson.id.startsWith('backend/http-caching/')).toBe(true);
    const page = await launchPage(`${s.base}/#lesson`);
    await page.waitFor(`document.querySelector('button[data-int="skip"]')`, 'Not for me button');
    await page.evaluate(`document.querySelector('button[data-int="skip"]').click()`);
    await waitUntil(() => s.readInterest()['backend/http-caching'] === 'skip', 'learner.json topic skip');
    expect(s.readInterest()).toEqual({ backend: 'deep', 'backend/http-caching': 'skip' });
    await page.waitFor(`document.querySelector('h1') && document.querySelector('h1').textContent === 'The TLS handshake'`, 'next lesson h1 "The TLS handshake"');
  }, 120_000);

  it.each([
    ['More like this', 'deep', 'basics'],
    ['Basics are enough', 'basics', 'deep'],
  ])('"%s" on a lesson writes the topic key %s, leaving the domain key untouched', async (label, value, domainValue) => {
    const s = await startServer(L({ backend: domainValue }));
    const shown = await s.getJson<{ lesson: { domain: string; topic: string } }>('/api/next');
    const key = `${shown.lesson.domain}/${shown.lesson.topic}`;
    const page = await launchPage(`${s.base}/#lesson`);
    await page.waitFor(`document.querySelector('button[data-int="${value}"]')`, `${label} button`);
    await page.evaluate(`[...document.querySelectorAll('button[data-int]')].find((b) => b.textContent.trim() === ${JSON.stringify(label)}).click()`);
    await waitUntil(() => s.readInterest()[key] === value, `learner.json ${key}=${value}`);
    expect(s.readInterest()).toEqual({ backend: domainValue, [key]: value });
  }, 120_000);
});

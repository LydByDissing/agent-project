// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.9,llm-dsl-2zv1.18 req=REQ-OPERATOR-EDU-006 c4=learn_app/learn_server]
//   [intent]Verifies GET/PUT /api/interest round-trips through learner.json, rejects bad keys and values without writing, makes a skipped topic disappear from selection, lets topic settings override domain settings, and routes an empty interest map to onboarding in the built SPA.[/intent]
//   [inv]A PUT that fails validation leaves learner.json byte-identical or absent; no test reaches the real claude binary.[/inv]
// [/origin]
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { makeApp } from './helpers/app.js';
import { canRunChromium, launchPage } from './helpers/browser.js';
import { FAKE, LEARN_APP, copyLearn, makeProject, startLearnServer } from './helpers/server.js';
import { tmp } from './helpers/tmp.js';

let savedEnv: Record<string, string | undefined> = {};
beforeAll(() => {
  savedEnv = { SDD_LEARN_HOME: process.env.SDD_LEARN_HOME, SDD_LEARN_CLAUDE: process.env.SDD_LEARN_CLAUDE };
  process.env.SDD_LEARN_HOME = tmp('learn-interest-');
  process.env.SDD_LEARN_CLAUDE = FAKE;
});
afterAll(() => {
  for (const [k, v] of Object.entries(savedEnv)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
});

function fixture(learner?: object) {
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
  const onDisk = (): { interest: Record<string, string> } => JSON.parse(readFileSync(learnerFile, 'utf8'));
  return { project, home, app, put, learnerFile, onDisk };
}

const L = (interest: Record<string, string>) => ({ schema: 1, interest, mastery: {}, history: [] });

describe('GET /api/interest', () => {
  it('returns an empty interest map and every domain and topic title from learn/', async () => {
    const f = fixture();
    const res = await f.app.request('/api/interest');
    const body = (await res.json()) as { interest: object; domains: Array<{ id: string; title: string; topics: Array<{ id: string; title: string }> }> };
    expect(res.status).toBe(200);
    expect(body.interest).toEqual({});
    expect(body.domains).toHaveLength(1);
    expect(body.domains[0].id).toBe('backend');
    expect(body.domains[0].title).toBe('Backend');
    const topics = [...body.domains[0].topics].sort((a, b) => a.id.localeCompare(b.id));
    expect(topics).toEqual([
      { id: 'backend/http-caching', title: 'HTTP caching' },
      { id: 'backend/tls-basics', title: 'TLS basics' },
    ]);
  });
});

describe('PUT /api/interest round-trip through learner.json', () => {
  it('PUT {key, value} writes learner.json and GET returns the same map', async () => {
    const f = fixture();
    const res = await f.put({ key: 'backend', value: 'deep' });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ interest: { backend: 'deep' } });
    expect(f.onDisk().interest).toEqual({ backend: 'deep' });
    const got = (await (await f.app.request('/api/interest')).json()) as { interest: object };
    expect(got.interest).toEqual({ backend: 'deep' });
  });

  it('a partial map is merged into the stored interest and keeps existing keys', async () => {
    const f = fixture(L({ backend: 'deep' }));
    const res = await f.put({ 'backend/http-caching': 'skip', 'backend/tls-basics': 'basics' });
    expect(res.status).toBe(200);
    expect(f.onDisk().interest).toEqual({ backend: 'deep', 'backend/http-caching': 'skip', 'backend/tls-basics': 'basics' });
  });
});

describe('PUT /api/interest validation writes nothing', () => {
  it('an unknown domain is a 400 naming the key and creates no learner.json', async () => {
    const f = fixture();
    const res = await f.put({ key: 'frontend', value: 'deep' });
    const body = (await res.json()) as { error: string; key: string; message: string };
    expect(res.status).toBe(400);
    expect(body.error).toBe('unknown_key');
    expect(body.key).toBe('frontend');
    expect(body.message).toContain('"frontend"');
    expect(existsSync(f.learnerFile)).toBe(false);
  });

  it('an unknown topic under a real domain is a 400 naming the key', async () => {
    const f = fixture();
    const res = await f.put({ key: 'backend/nope', value: 'skip' });
    expect(res.status).toBe(400);
    expect(((await res.json()) as { message: string }).message).toContain('"backend/nope"');
    expect(existsSync(f.learnerFile)).toBe(false);
  });

  it('a value outside deep|basics|skip is a 400 naming the value and leaves learner.json untouched', async () => {
    const f = fixture(L({ backend: 'basics' }));
    const before = readFileSync(f.learnerFile, 'utf8');
    const res = await f.put({ key: 'backend', value: 'maybe' });
    const body = (await res.json()) as { error: string; message: string };
    expect(res.status).toBe(400);
    expect(body.error).toBe('bad_value');
    expect(body.message).toContain('"maybe"');
    expect(readFileSync(f.learnerFile, 'utf8')).toBe(before);
  });

  it('a non-string value is a 400 naming the value', async () => {
    const f = fixture();
    const res = await f.put({ key: 'backend', value: 3 });
    expect(res.status).toBe(400);
    expect(((await res.json()) as { message: string }).message).toContain('3');
    expect(existsSync(f.learnerFile)).toBe(false);
  });

  it('a body that is not an object is a 400 bad_body', async () => {
    const f = fixture();
    expect((await f.put(undefined, 'not json')).status).toBe(400);
    expect((await f.put([['backend', 'deep']])).status).toBe(400);
    expect(((await (await f.put(null)).json()) as { error: string }).error).toBe('bad_body');
    expect(existsSync(f.learnerFile)).toBe(false);
  });
});

describe('"Not for me" flow at API level', () => {
  it('positive control: before the skip, /api/next returns a lesson from http-caching', async () => {
    const f = fixture(L({ backend: 'deep' }));
    const body = (await (await f.app.request('/api/next')).json()) as { lesson: { id: string } | null };
    expect(body.lesson?.id.startsWith('backend/http-caching/')).toBe(true);
  });

  it('after PUT topic skip, /api/next never returns a lesson of that topic', async () => {
    const f = fixture(L({ backend: 'deep' }));
    expect((await f.put({ key: 'backend/http-caching', value: 'skip' })).status).toBe(200);
    const body = (await (await f.app.request('/api/next')).json()) as { lesson: { id: string } | null };
    expect(body.lesson).not.toBeNull();
    expect(body.lesson!.id.startsWith('backend/http-caching/')).toBe(false);
    expect(body.lesson!.id).toBe('backend/tls-basics/01-handshake');
  });

  it('the skipped topic lessons are shown as skipped in /api/tree', async () => {
    const f = fixture(L({ backend: 'deep', 'backend/http-caching': 'skip' }));
    const tree = (await (await f.app.request('/api/tree')).json()) as {
      domains: Array<{ topics: Array<{ id: string; interest: string; lessons: Array<{ status: string }> }> }>;
    };
    const topic = tree.domains[0].topics.find((t) => t.id === 'backend/http-caching')!;
    expect(topic.interest).toBe('skip');
    expect(topic.lessons.length).toBeGreaterThan(0);
    expect(topic.lessons.every((l) => l.status === 'skipped')).toBe(true);
  });
});

describe('topic setting overrides domain setting', () => {
  it('domain deep with topic basics shows the topic as basics and its working lesson as not_at_basics', async () => {
    const f = fixture(L({ backend: 'deep', 'backend/http-caching': 'basics' }));
    const tree = (await (await f.app.request('/api/tree')).json()) as {
      domains: Array<{ interest: string; topics: Array<{ id: string; interest: string; lessons: Array<{ id: string; status: string }> }> }>;
    };
    expect(tree.domains[0].interest).toBe('deep');
    const http = tree.domains[0].topics.find((t) => t.id === 'backend/http-caching')!;
    const tls = tree.domains[0].topics.find((t) => t.id === 'backend/tls-basics')!;
    expect(http.interest).toBe('basics');
    expect(tls.interest).toBe('deep');
    expect(http.lessons.find((l) => l.id === 'backend/http-caching/02-revalidation')!.status).toBe('not_at_basics');
  });
});

describe('SPA bundle routes an empty interest map to onboarding', () => {
  const dist = join(LEARN_APP, 'dist');
  const bundle = (): string => {
    const js = readdirSync(join(dist, 'assets')).find((f) => f.endsWith('.js'));
    if (!js) throw new Error('no JS bundle in dist/assets');
    return readFileSync(join(dist, 'assets', js), 'utf8');
  };

  it('the bundle fetches /api/interest and carries the onboarding copy and lesson controls', () => {
    const js = bundle();
    expect(js).toContain('/api/interest');
    expect(js).toContain('#interests');
    expect(js).toContain('What do you want to get better at?');
    expect(js).toContain('Save and show my next lesson');
    expect(js).toContain('More like this');
    expect(js).toContain('Basics are enough');
    expect(js).toContain('Not for me');
  });

  it('index.html has the Lesson / Interests nav and the toast element', () => {
    const html = readFileSync(join(dist, 'index.html'), 'utf8');
    expect(html).toContain('href="#interests"');
    expect(html).toContain('href="#lesson"');
    expect(html).toContain('id="toast"');
  });
});

describe.skipIf(!canRunChromium)('headless Chromium onboarding render of the real server', () => {
  /** Serves a fresh project and returns the page's outerHTML once the SPA has rendered either screen. */
  const render = async (learner: object | null): Promise<string> => {
    const { project, home } = makeProject({ now: { jobs: [] }, learner });
    const srv = await startLearnServer({ project, home });
    const page = await launchPage(`${srv.base}/`);
    await page.waitFor(`document.querySelector('.onb') || document.querySelector('.quiz')`, 'onboarding or lesson view');
    return page.evaluate<string>('document.documentElement.outerHTML');
  };

  it('an empty learner.json lands on the onboarding screen listing the domains', async () => {
    const dom = await render(null);
    expect(dom).toContain('What do you want to get better at?');
    expect(dom).toContain('Backend');
    expect(dom).toContain('Save and show my next lesson');
    expect(dom).not.toContain('Check yourself');
  }, 90_000);

  it('a learner with interests lands on the lesson view, not onboarding', async () => {
    const dom = await render(L({ backend: 'deep' }));
    expect(dom).toContain('Check yourself');
    expect(dom).not.toContain('What do you want to get better at?');
  }, 90_000);
});

// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.5 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_server]
//   [intent]Exercises /api/now, learner, tree, next, lesson and asset against the seed lessons, and the real bundled server creating learner.json.[/intent]
// [/origin]
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { makeApp } from './helpers/app.js';
import { REPO, makeProject, startLearnServer } from './helpers/server.js';
import { tmp as tmpDir } from './helpers/tmp.js';

const tmp = (): string => tmpDir('learn-api-');

function fixture(learner?: object, now?: object) {
  const project = tmp();
  const home = tmp();
  cpSync(join(REPO, 'learn'), join(project, 'learn'), { recursive: true });
  if (now) {
    mkdirSync(join(project, '.sdd'));
    writeFileSync(join(project, '.sdd', 'now.json'), JSON.stringify(now));
  }
  if (learner) writeFileSync(join(home, 'learner.json'), JSON.stringify(learner));
  const app = makeApp({ project, distDir: project, home });
  return { project, home, app, get: async (p: string) => app.request(p) };
}
const NOW = {
  run: 'r1', wave: 1,
  jobs: [
    { id: 't1', title: 'Cache headers', topics: ['backend/http-caching'], status: 'running' },
    { id: 't4', title: 'Grid layout', topics: ['frontend/css-grid'], status: 'running' },
  ],
};
const L = (o: object) => ({ schema: 1, interest: { backend: 'deep', frontend: 'skip' }, mastery: {}, history: [], ...o });

describe('GET /api/now', () => {
  it('returns {jobs:[]} when now.json is absent', async () => {
    const f = fixture();
    expect(await (await f.get('/api/now')).json()).toEqual({ jobs: [] });
  });
  it('returns now.json content', async () => {
    const f = fixture(undefined, NOW);
    expect(await (await f.get('/api/now')).json()).toEqual(NOW);
  });
  it('reports a named error for corrupt now.json', async () => {
    const f = fixture();
    mkdirSync(join(f.project, '.sdd'));
    writeFileSync(join(f.project, '.sdd', 'now.json'), '{nope');
    const res = await f.get('/api/now');
    expect(res.status).toBe(500);
    expect((await res.json()).error).toBe('now_invalid');
  });
});

describe('GET /api/next', () => {
  it('acceptance: first http-caching lesson plus what_changed for frontend/css-grid', async () => {
    const f = fixture(L({}), NOW);
    const body = await (await f.get('/api/next')).json();
    expect(body.lesson.id).toBe('backend/http-caching/01-freshness');
    expect(body.what_changed).toEqual([
      { topic: 'frontend/css-grid', interest: 'skip', jobs: [{ id: 't4', title: 'Grid layout', status: 'running' }] },
    ]);
    expect(body.reason).toContain('t1 Cache headers');
  });
  it('advances to lesson 2 when lesson 1 reaches box 3', async () => {
    const f = fixture(L({ mastery: { 'backend/http-caching/01-freshness': { box: 3, due: '2099-01-01' } } }), NOW);
    expect((await (await f.get('/api/next')).json()).lesson.id).toBe('backend/http-caching/02-revalidation');
  });
  it('basics gives only intro lessons', async () => {
    const f = fixture(L({ interest: { backend: 'basics' }, mastery: { 'backend/http-caching/01-freshness': { box: 5, due: '2000-01-01' } } }), NOW);
    expect((await (await f.get('/api/next')).json()).lesson.id).toBe('backend/http-caching/01-freshness');
  });
  it('never returns box-5 not-due lessons (lesson null when only those remain)', async () => {
    const f = fixture(L({ interest: { backend: 'deep' }, mastery: { 'backend/http-caching/01-freshness': { box: 5, due: '2099-01-01' }, 'backend/http-caching/02-revalidation': { box: 5, due: '2099-01-01' } } }), NOW);
    expect((await (await f.get('/api/next')).json()).lesson).toBeNull();
  });
  it('with no now.json returns a lesson via review ranking and is deterministic', async () => {
    const f = fixture(L({}));
    const a = await (await f.get('/api/next')).json();
    const b = await (await f.get('/api/next')).json();
    expect(a.lesson.id).toBe('backend/http-caching/01-freshness');
    expect(b).toEqual(a);
  });
});

describe('GET /api/tree and /api/learner', () => {
  it('lists topics with per-lesson mastery and status', async () => {
    const f = fixture(L({ interest: { backend: 'basics' }, mastery: { 'backend/http-caching/01-freshness': { box: 2, due: '2026-11-22' } } }));
    const tree = await (await f.get('/api/tree')).json();
    const topic = tree.domains[0].topics[0];
    expect(tree.domains[0].interest).toBe('basics');
    expect(topic.id).toBe('backend/http-caching');
    expect(topic.lessons[0]).toMatchObject({ id: 'backend/http-caching/01-freshness', mastery: { box: 2, due: '2026-11-22' }, status: 'learning' });
    expect(topic.lessons[1]).toMatchObject({ mastery: null, status: 'not_at_basics' });
  });
  it('marks locked lessons when prerequisites are unmet at deep', async () => {
    const f = fixture(L({}));
    const topic = (await (await f.get('/api/tree')).json()).domains[0].topics[0];
    expect(topic.lessons[1].status).toBe('locked');
  });
  it('returns learner state', async () => {
    const f = fixture(L({}));
    expect((await (await f.get('/api/learner')).json()).schema).toBe(1);
  });
});

describe('GET /api/lesson/* and /api/asset/*', () => {
  it('returns front matter and Markdown body for a lesson id with slashes', async () => {
    const f = fixture(L({}));
    const res = await f.get('/api/lesson/backend/http-caching/02-revalidation');
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({ id: 'backend/http-caching/02-revalidation', level: 'working', topic_position: 2, topic_size: 2 });
    expect(body.requires).toEqual([{ id: 'backend/http-caching/01-freshness', title: expect.any(String), mastered: false }]);
    expect(body.sources.length).toBeGreaterThan(0);
    expect(body.body).toContain('![');
    expect(body.body).not.toContain('requires:');
  });
  it('accepts an encoded-slash id', async () => {
    const f = fixture(L({}));
    expect((await f.get('/api/lesson/backend%2Fhttp-caching%2F01-freshness')).status).toBe(200);
  });
  it.each(['/api/lesson/../../secret', '/api/lesson/..%2F..%2Fsecret', '/api/lesson/backend/../../x', '/api/lesson/backend/http-caching/99-nope'])('404s %s', async (p) => {
    const f = fixture(L({}));
    expect((await f.get(p)).status).toBe(404);
  });
  it('serves lesson SVGs as image/svg+xml', async () => {
    const f = fixture(L({}));
    const res = await f.get('/api/asset/backend/http-caching/diagrams/revalidation.svg');
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toBe('image/svg+xml');
    expect(await res.text()).toContain('<svg');
  });
  it.each([
    '/api/asset/../.sdd/now.json',
    '/api/asset/..%2F..%2Fpackage.svg',
    '/api/asset/backend/http-caching/01-freshness.md',
    '/api/asset/backend/http-caching/diagrams/missing.svg',
  ])('404s asset %s', async (p) => {
    const f = fixture(L({}), NOW);
    writeFileSync(join(f.project, 'outside.svg'), '<svg/>');
    expect((await f.get(p)).status).toBe(404);
    expect((await f.get('/api/asset/..%2Foutside.svg')).status).toBe(404);
  });
});

describe('bundled server.js start', () => {
  it('creates learner.json on start and serves /api/next and /api/lesson', async () => {
    const { project } = makeProject({ now: NOW });
    const home = join(tmp(), 'home');
    const srv = await startLearnServer({ project, home, claude: null });
    expect(JSON.parse(readFileSync(join(home, 'learner.json'), 'utf8'))).toEqual({ schema: 1, interest: {}, mastery: {}, history: [] });
    const next = await (await fetch(`${srv.base}/api/next`)).json();
    expect(next.lesson.id).toBe('backend/http-caching/01-freshness');
    const lesson = await fetch(`${srv.base}/api/lesson/${next.lesson.id}`);
    expect(lesson.status).toBe(200);
    expect(existsSync(join(project, 'learner.json'))).toBe(false);
  }, 20_000);
});

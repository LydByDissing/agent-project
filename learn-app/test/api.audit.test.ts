// [origin ref=llm-dsl-gu1y.6 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_server]
//   [intent]Audits the JSON API against the t3 contract: now.json changes show on the next request (no caching), the wave run feeds what_changed, and only SVG assets under learn/ are served.[/intent]
// [/origin]
import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { makeApp } from './helpers/app.js';

const LEARN_APP = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = resolve(LEARN_APP, '..');
const tmp = (): string => mkdtempSync(join(tmpdir(), 'learn-api-audit-'));

interface Job {
  id: string;
  title: string;
  topics: string[];
  status: string;
}

function fixture() {
  const project = tmp();
  const home = tmp();
  const distDir = tmp();
  cpSync(join(REPO, 'learn'), join(project, 'learn'), { recursive: true, preserveTimestamps: true });
  const app = makeApp({ project, distDir, home });
  const writeNow = (jobs: Job[]): void => {
    mkdirSync(join(project, '.sdd'), { recursive: true });
    writeFileSync(join(project, '.sdd', 'now.json'), JSON.stringify({ run: 'r1', wave: 1, jobs }));
  };
  const removeNow = (): void => rmSync(join(project, '.sdd', 'now.json'), { force: true });
  return { project, home, get: async (p: string) => app.request(p), writeNow, removeNow };
}

const job = (id: string, title: string, topics: string[], status: string): Job => ({ id, title, topics, status });

describe('now.json changes show on the next request', () => {
  it('GET /api/now returns the status change written after the first request', async () => {
    const f = fixture();
    f.writeNow([job('t1', 'Cache headers', ['backend/http-caching'], 'running')]);
    expect(await (await f.get('/api/now')).json()).toMatchObject({ jobs: [{ id: 't1', status: 'running' }] });

    f.writeNow([job('t1', 'Cache headers', ['backend/http-caching'], 'done')]);

    expect(await (await f.get('/api/now')).json()).toMatchObject({ jobs: [{ id: 't1', status: 'done' }] });
  });

  it('GET /api/now returns {jobs:[]} once now.json is removed after having jobs', async () => {
    const f = fixture();
    f.writeNow([job('t1', 'Cache headers', ['backend/http-caching'], 'running')]);
    expect((await (await f.get('/api/now')).json()).jobs).toHaveLength(1);

    f.removeNow();

    expect(await (await f.get('/api/now')).json()).toEqual({ jobs: [] });
  });

  it('GET /api/next drops a skipped-topic note once its job is done', async () => {
    const f = fixture();
    writeFileSync(join(f.home, 'learner.json'), JSON.stringify({ schema: 1, interest: { frontend: 'skip' }, mastery: {}, history: [] }));
    f.writeNow([job('t4', 'Grid layout', ['frontend/css-grid'], 'running')]);
    const first = await (await f.get('/api/next')).json();
    expect(first.what_changed).toEqual([
      { topic: 'frontend/css-grid', interest: 'skip', jobs: [{ id: 't4', title: 'Grid layout', status: 'running' }] },
    ]);

    f.writeNow([job('t4', 'Grid layout', ['frontend/css-grid'], 'done')]);

    expect((await (await f.get('/api/next')).json()).what_changed).toEqual([]);
  });
});

describe('GET /api/asset/* accepts only SVG under learn/', () => {
  it('serves a real lesson SVG (positive control for the rejections below)', async () => {
    const f = fixture();
    const res = await f.get('/api/asset/backend/http-caching/diagrams/revalidation.svg');
    expect(res.status).toBe(200);
    expect(await res.text()).toContain('<svg');
  });

  it.each([
    ['diagram source .puml', '/api/asset/backend/http-caching/diagrams/revalidation.puml'],
    ['lesson markdown', '/api/asset/backend/http-caching/01-freshness.md'],
    ['index.yaml', '/api/asset/backend/http-caching/index.yaml'],
    ['svg suffix with trailing text', '/api/asset/backend/http-caching/diagrams/revalidation.svg.md'],
  ])('rejects %s with 404', async (_label, p) => {
    const f = fixture();
    const res = await f.get(p);
    expect(res.status).toBe(404);
    expect(await res.text()).not.toContain('title:');
  });

  it.each([
    ['encoded dot-dot slash', '/api/asset/%2e%2e%2foutside.svg'],
    ['dot-dot then encoded slash', '/api/asset/..%2Foutside.svg'],
    ['encoded leading slash then traversal', '/api/asset/%2F..%2Foutside.svg'],
    ['traversal through a real topic folder', '/api/asset/backend%2F..%2F..%2Foutside.svg'],
  ])('rejects traversal (%s) and never returns the file outside learn/', async (_label, p) => {
    const f = fixture();
    writeFileSync(join(f.project, 'outside.svg'), '<svg>OUTSIDE</svg>');
    const res = await f.get(p);
    expect(res.status).toBe(404);
    expect(await res.text()).not.toContain('OUTSIDE');
  });
});

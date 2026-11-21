// [origin ref=llm-dsl-gu1y.1 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Verifies health, SPA serving, 404 path-traversal handling and stub routes of the server app.[/intent]
// [/origin]
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { createApp } from '../src/server/app.js';
import { PathEscapeError, resolveUnder } from '../src/server/paths.js';

const dist = mkdtempSync(join(tmpdir(), 'learn-dist-'));
writeFileSync(join(dist, 'index.html'), '<title>SDD Learn</title>');
writeFileSync(join(dist, '..', 'secret.txt'), 'secret');
const app = createApp({ project: dist, distDir: dist });

describe('server app', () => {
  it('reports health', async () => {
    const res = await app.request('/api/health');
    expect(await res.json()).toEqual({ ok: true });
  });
  it('serves the SPA shell at /', async () => {
    const res = await app.request('/');
    expect(res.status).toBe(200);
    expect(await res.text()).toContain('SDD Learn');
  });
  it('404s encoded traversal on the lesson API', async () => {
    const res = await app.request('/api/lesson/..%2F..%2Fetc%2Fpasswd');
    expect(res.status).toBe(404);
  });
  it('404s traversal on static paths', async () => {
    expect((await app.request('/..%2Fsecret.txt')).status).toBe(404);
    expect((await app.request('/%2e%2e/secret.txt')).status).toBe(404);
  });
  it('stubs valid lesson ids with 501', async () => {
    expect((await app.request('/api/lesson/intro-01')).status).toBe(501);
  });
});

describe('resolveUnder', () => {
  it('allows children and rejects escapes', () => {
    expect(resolveUnder('/a/b', 'c/d')).toBe('/a/b/c/d');
    expect(() => resolveUnder('/a/b', '../x')).toThrow(PathEscapeError);
    expect(() => resolveUnder('/a/b', 'c\0')).toThrow(PathEscapeError);
  });
});

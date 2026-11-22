// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.2 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Pins the Hono app contract for stub routes, unknown API paths and path-resolution edge cases that the coder's smoke tests do not cover.[/intent]
// [/origin]
import { writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';
import { makeApp } from './helpers/app.js';
import { tmp } from './helpers/tmp.js';
import { PathEscapeError, resolveUnder } from '../src/server/paths.js';

let app: ReturnType<typeof makeApp>;

beforeAll(() => {
  const dist = tmp('learn-contract-dist-');
  writeFileSync(join(dist, 'index.html'), '<title>SDD Learn</title>');
  app = makeApp({ project: dist, distDir: dist, home: tmp('learn-contract-home-') });
});

describe('API contract', () => {
  it('lesson route with an unknown id returns 404 with named error not_found', async () => {
    const res = await app.request('/api/lesson/intro-01');
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: 'not_found' });
  });

  it('lesson route with an id starting with an underscore returns 404 with named error not_found', async () => {
    const res = await app.request('/api/lesson/_hidden');
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: 'not_found' });
  });

  it('unknown API path returns 404 with named error not_found', async () => {
    const res = await app.request('/api/does-not-exist');
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: 'not_found' });
  });

  it('POST to health is not routed as a GET and returns 404', async () => {
    const res = await app.request('/api/health', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    expect(res.status).toBe(404);
  });
});

describe('SPA serving', () => {
  it('root path returns index.html with text/html content type', async () => {
    const res = await app.request('/');
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toContain('text/html');
    expect(await res.text()).toContain('<title>SDD Learn</title>');
  });

  it('missing static file returns 404 rather than an unhandled error', async () => {
    const res = await app.request('/no-such-file.js');
    expect(res.status).toBe(404);
  });
});

describe('resolveUnder edge cases', () => {
  const root = resolve('/srv/project/learn');

  it('a null byte in the request is rejected as an escape', () => {
    expect(() => resolveUnder(root, 'c\0')).toThrow(PathEscapeError);
  });

  it('empty request resolves to the root itself', () => {
    expect(resolveUnder(root, '')).toBe(root);
  });

  it('leading slash in request is treated as relative to the root, not the filesystem root', () => {
    expect(resolveUnder(root, '/etc/passwd')).toBe(join(root, 'etc', 'passwd'));
  });

  it('sibling directory sharing the root name as a prefix is rejected', () => {
    expect(() => resolveUnder(root, '../learn-evil/secret')).toThrow(PathEscapeError);
  });

  it('nested traversal that climbs out and back in still resolves inside the root', () => {
    expect(resolveUnder(root, 'a/../b/c')).toBe(join(root, 'b', 'c'));
  });

  it('traversal that climbs above the root is rejected with the requested path in the error', () => {
    expect(() => resolveUnder(root, 'a/../../../etc/passwd')).toThrow(/escapes root/);
  });
});

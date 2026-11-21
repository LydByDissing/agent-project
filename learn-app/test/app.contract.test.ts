// [origin ref=llm-dsl-gu1y.2 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Pins the Hono app contract for stub routes, unknown API paths and path-resolution edge cases that the coder's smoke tests do not cover.[/intent]
// [/origin]
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';
import { createApp } from '../src/server/app.js';
import { PathEscapeError, resolveUnder } from '../src/server/paths.js';

let app: ReturnType<typeof createApp>;

beforeAll(() => {
  const dist = mkdtempSync(join(tmpdir(), 'learn-contract-dist-'));
  writeFileSync(join(dist, 'index.html'), '<title>SDD Learn</title>');
  app = createApp({ project: dist, distDir: dist });
});

describe('API stub routes', () => {
  it.each(['/api/now', '/api/learner', '/api/tree', '/api/next'])(
    '%s returns 501 with named error not_implemented',
    async (path) => {
      const res = await app.request(path);
      expect(res.status).toBe(501);
      expect(await res.json()).toEqual({ error: 'not_implemented' });
    },
  );

  it('lesson route with a valid id returns 501 with named error not_implemented', async () => {
    const res = await app.request('/api/lesson/intro-01');
    expect(res.status).toBe(501);
    expect(await res.json()).toEqual({ error: 'not_implemented' });
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
    const res = await app.request('/api/health', { method: 'POST' });
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

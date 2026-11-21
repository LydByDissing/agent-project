// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.1 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Verifies health and encoded path-traversal handling of the server app against a secret file placed next to dist inside a private temp root.[/intent]
// [/origin]
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';
import { makeApp } from './helpers/app.js';
import { tmp } from './helpers/tmp.js';

let app: ReturnType<typeof makeApp>;

beforeAll(() => {
  // root/secret.txt sits exactly where ../secret.txt from root/dist resolves, so an escape would succeed if the guard failed.
  const root = tmp('learn-app-root-');
  const dist = join(root, 'dist');
  mkdirSync(dist);
  writeFileSync(join(dist, 'index.html'), '<title>SDD Learn</title>');
  writeFileSync(join(root, 'secret.txt'), 'secret');
  app = makeApp({ project: dist, distDir: dist, home: tmp('learn-app-home-') });
});

describe('server app', () => {
  it('reports health', async () => {
    const res = await app.request('/api/health');
    expect(await res.json()).toEqual({ ok: true });
  });
  it('404s encoded traversal on the lesson API', async () => {
    const res = await app.request('/api/lesson/..%2F..%2Fetc%2Fpasswd');
    expect(res.status).toBe(404);
  });
  it('404s traversal on static paths and never returns the secret', async () => {
    for (const p of ['/..%2Fsecret.txt', '/%2e%2e/secret.txt']) {
      const res = await app.request(p);
      expect(res.status).toBe(404);
      expect(await res.text()).not.toContain('secret');
    }
  });
});

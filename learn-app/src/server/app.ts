// [origin ref=llm-dsl-gu1y.1 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Builds the Hono app: JSON API skeleton plus static serving of the built SPA.[/intent]
// [/origin]
import { readFile } from 'node:fs/promises';
import { extname } from 'node:path';
import { Hono } from 'hono';
import { PathEscapeError, resolveUnder } from './paths.js';

export interface AppOptions {
  project: string;
  distDir: string;
}

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
  '.ico': 'image/x-icon',
};

const LESSON_ID = /^[a-z0-9][a-z0-9._-]*$/i;

export function createApp({ distDir }: AppOptions): Hono {
  const app = new Hono();

  app.get('/api/health', (c) => c.json({ ok: true }));

  app.get('/api/lesson/:id', (c) => {
    if (!LESSON_ID.test(c.req.param('id'))) return c.json({ error: 'not_found' }, 404);
    return c.json({ error: 'not_implemented' }, 501);
  });

  for (const route of ['/api/now', '/api/learner', '/api/tree', '/api/next']) {
    app.get(route, (c) => c.json({ error: 'not_implemented' }, 501));
  }
  app.all('/api/*', (c) => c.json({ error: 'not_found' }, 404));

  app.get('*', async (c) => {
    let pathname: string;
    try {
      pathname = decodeURIComponent(new URL(c.req.url).pathname);
    } catch {
      return c.text('Not found', 404);
    }
    try {
      const file = resolveUnder(distDir, pathname === '/' ? 'index.html' : pathname);
      const body = await readFile(file);
      return c.body(body, 200, { 'Content-Type': MIME[extname(file)] ?? 'application/octet-stream' });
    } catch (err) {
      if (err instanceof PathEscapeError || (err as NodeJS.ErrnoException).code) return c.text('Not found', 404);
      throw err;
    }
  });

  return app;
}

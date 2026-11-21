// [origin ref=llm-dsl-gu1y.16 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Test helper that builds the app for a fixed port and makes app.request send the matching Host header, so tests pass the origin guard instead of weakening it.[/intent]
// [/origin]
import type { Hono } from 'hono';
import { type AppOptions, createApp } from '../../src/server/app.js';

export const TEST_PORT = 4747;
export const TEST_HOST = `127.0.0.1:${TEST_PORT}`;

export function makeApp(opts: Omit<AppOptions, 'port'> & { port?: number }): Omit<Hono, 'request'> & { request: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> } {
  const port = opts.port ?? TEST_PORT;
  const app = createApp({ ...opts, port });
  const orig = app.request.bind(app) as (input: RequestInfo | URL, init?: RequestInit) => Response | Promise<Response>;
  app.request = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(init.headers).forEach((v, k) => headers.set(k, v));
    if (!headers.has('host')) headers.set('host', `127.0.0.1:${port}`);
    return await orig(input, { ...init, headers });
  }) as Hono['request'];
  return app as ReturnType<typeof makeApp>;
}

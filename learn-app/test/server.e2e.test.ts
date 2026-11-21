// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.2 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Runs the real bundled learn-app/server.js as a child process to verify loopback binding (bind address and refused LAN connect), default port 4747, SPA shell, health, traversal rejection and no-node_modules startup.[/intent]
// [/origin]
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { request as httpRequest } from 'node:http';
import { networkInterfaces } from 'node:os';
import { join } from 'node:path';
import { connect } from 'node:net';
import { isBuiltin } from 'node:module';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { LEARN_APP, freePort, makeProject, startLearnServer, type RunningServer } from './helpers/server.js';
import { tmp } from './helpers/tmp.js';

const BUNDLE = join(LEARN_APP, 'server.js');
const POC = join(LEARN_APP, 'design', 'poc.html');
const SERVER_START_TIMEOUT_MS = 10_000;

type Running = RunningServer;

const startServer = (script: string, project: string): Promise<Running> =>
  startLearnServer({ project, home: tmp('learn-e2e-home-'), script, claude: null });

/** Raw HTTP request: sends the path byte-for-byte, so WHATWG URL normalisation cannot hide traversal attempts. */
function rawGet(port: number, path: string, host = '127.0.0.1'): Promise<{ status: number; body: string; type: string }> {
  return new Promise((resolveReq, reject) => {
    const req = httpRequest({ host, port, path, method: 'GET' }, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () =>
        resolveReq({
          status: res.statusCode ?? 0,
          body: Buffer.concat(chunks).toString('utf8'),
          type: String(res.headers['content-type'] ?? ''),
        }),
      );
    });
    req.on('error', reject);
    req.end();
  });
}

const stop = (running: Running | undefined): Promise<void> => running?.stop() ?? Promise.resolve();

// --- Real bundle, run exactly as the acceptance criterion states -------------------------------

describe('bundled learn-app/server.js on loopback', () => {
  let root: string;
  let running: Running;

  beforeAll(async () => {
    root = tmp('learn-e2e-');
    mkdirSync(join(root, 'project'));
    running = await startServer(BUNDLE, join(root, 'project'));
  }, SERVER_START_TIMEOUT_MS + 5_000);

  afterAll(async () => {
    await stop(running);
  });

  it('GET / on 127.0.0.1 returns the SPA shell with an empty wave strip', async () => {
    const res = await rawGet(running.port, '/');
    expect(res.status).toBe(200);
    expect(res.type).toContain('text/html');
    expect(res.body).toContain('<div class="brand">SDD Learn</div>');
    expect(res.body).toMatch(/<div class="wave" id="wave" aria-live="polite"><\/div>/);
  });

  it('GET /api/health on 127.0.0.1 returns exactly {ok:true}', async () => {
    const res = await rawGet(running.port, '/api/health');
    expect(res.status).toBe(200);
    expect(JSON.parse(res.body)).toEqual({ ok: true });
  });

  it('served stylesheet declares every light-theme colour and font token from design/poc.html', async () => {
    const shell = (await rawGet(running.port, '/')).body;
    const cssHref = shell.match(/<link rel="stylesheet" crossorigin href="(\.\/assets\/[^"]+\.css)">/)?.[1];
    expect(cssHref).toBeDefined();
    const css = (await rawGet(running.port, '/' + cssHref!.replace(/^\.\//, ''))).body.replace(/\s+/g, '');

    const poc = readFileSync(POC, 'utf8');
    const lightRoot = poc.match(/:root\{([^}]*)\}/)?.[1] ?? '';
    const tokens = [...lightRoot.matchAll(/(--[a-z-]+):([^;]+);/g)].map((m) => `${m[1]}:${m[2].trim()}`);
    expect(tokens.length).toBeGreaterThan(5);
    for (const token of tokens) {
      expect(css, `missing token ${token}`).toContain(token.replace(/\s+/g, ''));
    }
  });

  it.skipIf(process.platform !== 'linux')('the listening socket is bound to 127.0.0.1 only (/proc/net/tcp shows 0100007F, never 00000000)', () => {
    const portHex = running.port.toString(16).toUpperCase().padStart(4, '0');
    const LISTEN = '0A';
    const rows = readFileSync('/proc/net/tcp', 'utf8').split('\n').slice(1).map((l) => l.trim().split(/\s+/));
    const listeners = rows.filter((c) => c[3] === LISTEN && c[1]?.endsWith(`:${portHex}`)).map((c) => c[1].split(':')[0]);
    expect(listeners, `no IPv4 listener found on port ${running.port}`).not.toEqual([]);
    expect(listeners).toEqual(['0100007F']);
    const v6 = existsSync('/proc/net/tcp6')
      ? readFileSync('/proc/net/tcp6', 'utf8').split('\n').slice(1).map((l) => l.trim().split(/\s+/)).filter((c) => c[3] === LISTEN && c[1]?.endsWith(`:${portHex}`))
      : [];
    expect(v6, 'server must not also listen on an IPv6 wildcard').toEqual([]);
  });

  const lan = Object.values(networkInterfaces())
    .flat()
    .find((a) => a && a.family === 'IPv4' && !a.internal)?.address;

  // Only ECONNREFUSED proves "not bound"; a timeout would mean a firewall drop and proves nothing.
  it.skipIf(!lan)('a TCP connect to the LAN address on the server port is refused with ECONNREFUSED', async () => {
    expect((await rawGet(running.port, '/api/health')).status, 'positive control: loopback must answer').toBe(200);
    const outcome = await new Promise<string>((resolveConn) => {
      const socket = connect({ host: lan!, port: running.port });
      socket.setTimeout(2000);
      socket.once('connect', () => {
        socket.destroy();
        resolveConn('connected');
      });
      socket.once('error', (e: NodeJS.ErrnoException) => resolveConn(e.code ?? 'error'));
      socket.once('timeout', () => {
        socket.destroy();
        resolveConn('timeout');
      });
    });
    expect(outcome).toBe('ECONNREFUSED');
  });

  it('bundle imports only Node built-ins so it runs without node_modules', () => {
    const source = readFileSync(BUNDLE, 'utf8');
    const specifiers = [
      ...source.matchAll(/\bfrom\s+"([^"]+)"/g),
      ...source.matchAll(/\brequire\("([^"]+)"\)/g),
      ...source.matchAll(/\bimport\("([^"]+)"\)/g),
    ].map((m) => m[1]);
    expect(specifiers.length).toBeGreaterThan(0);
    const external = specifiers.filter((s) => !isBuiltin(s));
    expect(external).toEqual([]);
    expect(source).not.toMatch(/require\(["']hono/);
  });
});

// --- Copy of the bundle outside the repo: no node_modules anywhere up the tree -----------------

describe('bundle copy with no node_modules ancestor', () => {
  let root: string;
  let running: Running;
  const SECRET = 'TOP-SECRET-FIXTURE';

  beforeAll(async () => {
    root = tmp('learn-trav-');
    const app = join(root, 'app');
    mkdirSync(app, { recursive: true });
    cpSync(BUNDLE, join(app, 'server.js'));
    cpSync(join(LEARN_APP, 'dist'), join(app, 'dist'), { recursive: true });
    // Sits exactly where ../secret.txt from dist/ resolves, so an escape would succeed if the guard failed.
    writeFileSync(join(app, 'secret.txt'), SECRET);
    mkdirSync(join(root, 'project'));
    running = await startServer(join(app, 'server.js'), join(root, 'project'));
  }, SERVER_START_TIMEOUT_MS + 5_000);

  afterAll(async () => {
    await stop(running);
  });

  it('bundle copy outside the repo starts and answers /api/health', async () => {
    const res = await rawGet(running.port, '/api/health');
    expect(res.status).toBe(200);
    expect(JSON.parse(res.body)).toEqual({ ok: true });
  });

  it('static asset inside dist is served with 200 so the traversal probes below are meaningful', async () => {
    const res = await rawGet(running.port, '/index.html');
    expect(res.status).toBe(200);
    expect(res.body).toContain('SDD Learn');
  });

  it.each([
    ['encoded ../', '/..%2Fsecret.txt'],
    ['partially encoded ../', '/.%2e%2Fsecret.txt'],
    ['double-encoded ../', '/%252e%252e%252fsecret.txt'],
    ['double-encoded ../ with dot segment', '/%252e%252e/secret.txt'],
    ['backslash ..\\', '/..%5Csecret.txt'],
    ['null byte suffix', '/index.html%00'],
    ['null byte before escape', '/%00/../secret.txt'],
  ])('static path with %s returns 404 and never serves the secret', async (_label, path) => {
    const res = await rawGet(running.port, path);
    expect(res.status).toBe(404);
    expect(res.body).not.toContain(SECRET);
  });

  it.each([
    ['encoded ../', '/api/lesson/..%2F..%2Fsecret'],
    ['double-encoded ../', '/api/lesson/%252e%252e%252fsecret'],
    ['backslash ..\\', '/api/lesson/..%5C..%5Csecret'],
    ['null byte suffix', '/api/lesson/intro-01%00'],
    ['leading underscore', '/api/lesson/_secret'],
  ])('lesson API with %s returns 404 named not_found', async (_label, path) => {
    const res = await rawGet(running.port, path);
    expect(res.status).toBe(404);
    expect(JSON.parse(res.body)).toEqual({ error: 'not_found' });
    expect(res.body).not.toContain(SECRET);
  });

  it('lesson API with an unknown id returns 404 named not_found', async () => {
    const res = await rawGet(running.port, '/api/lesson/intro-01');
    expect(res.status).toBe(404);
    expect(JSON.parse(res.body)).toEqual({ error: 'not_found' });
  });

  it('now API answers with an empty job list when no run is published', async () => {
    const res = await rawGet(running.port, '/api/now');
    expect(res.status).toBe(200);
    expect(JSON.parse(res.body)).toEqual({ jobs: [] });
  });
});

// --- Default port ---------------------------------------------------------------------------------

/** True when something already listens on 127.0.0.1:port. */
async function portInUse(port: number): Promise<boolean> {
  return new Promise((res) => {
    const socket = connect({ host: '127.0.0.1', port });
    socket.once('connect', () => {
      socket.destroy();
      res(true);
    });
    socket.once('error', () => res(false));
  });
}

const DEFAULT_PORT = 4747;
const defaultPortBusy = await portInUse(DEFAULT_PORT);

describe('default port', () => {
  // Visible skip: 4747 belongs to somebody else on this machine, so the default cannot be observed.
  it.skipIf(defaultPortBusy)('listens on 4747 when SDD_LEARN_PORT is unset', async () => {
    const { project, home } = makeProject({});
    const srv = await startLearnServer({ project, home, port: null, claude: null });
    expect(srv.stdout()).toContain(`http://127.0.0.1:${DEFAULT_PORT}`);
    const res = await rawGet(DEFAULT_PORT, '/api/health', '127.0.0.1');
    expect(res.status).toBe(200);
    expect(JSON.parse(res.body)).toEqual({ ok: true });
  }, 20_000);
});

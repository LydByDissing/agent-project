// [origin ref=llm-dsl-gu1y.2 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Runs the real bundled learn-app/server.js as a child process to verify loopback binding, SPA shell, health, traversal rejection and no-node_modules startup.[/intent]
// [/origin]
import { spawn, type ChildProcess } from 'node:child_process';
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { request as httpRequest, createServer } from 'node:http';
import { networkInterfaces, tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { connect } from 'node:net';
import { fileURLToPath } from 'node:url';
import { isBuiltin } from 'node:module';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const LEARN_APP = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const BUNDLE = join(LEARN_APP, 'server.js');
const POC = join(LEARN_APP, 'design', 'poc.html');
const SERVER_START_TIMEOUT_MS = 10_000;

interface Running {
  child: ChildProcess;
  port: number;
  stderr: () => string;
}

function freePort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const probe = createServer();
    probe.unref();
    probe.on('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const address = probe.address();
      if (typeof address === 'object' && address) {
        const port = address.port;
        probe.close(() => resolvePort(port));
      } else {
        reject(new Error('no port'));
      }
    });
  });
}

async function startServer(script: string, project: string): Promise<Running> {
  const port = await freePort();
  const child = spawn(process.execPath, [script, '--project', project], {
    env: { ...process.env, SDD_LEARN_PORT: String(port) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stdout = '';
  let stderr = '';
  child.stdout!.on('data', (d: Buffer) => (stdout += d.toString()));
  child.stderr!.on('data', (d: Buffer) => (stderr += d.toString()));
  await new Promise<void>((resolveReady, reject) => {
    const timer = setTimeout(() => reject(new Error(`server did not start: ${stderr}`)), SERVER_START_TIMEOUT_MS);
    const poll = setInterval(() => {
      if (stdout.includes('listening')) {
        clearTimeout(timer);
        clearInterval(poll);
        resolveReady();
      } else if (child.exitCode !== null) {
        clearTimeout(timer);
        clearInterval(poll);
        reject(new Error(`server exited ${child.exitCode}: ${stderr}`));
      }
    }, 20);
  });
  return { child, port, stderr: () => stderr };
}

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

function stop(running: Running | undefined): void {
  if (running && running.child.exitCode === null) running.child.kill('SIGTERM');
}

// --- Real bundle, run exactly as the acceptance criterion states -------------------------------

describe('bundled learn-app/server.js on loopback', () => {
  let root: string;
  let running: Running;

  beforeAll(async () => {
    root = mkdtempSync(join(tmpdir(), 'learn-e2e-'));
    mkdirSync(join(root, 'project'));
    running = await startServer(BUNDLE, join(root, 'project'));
  }, SERVER_START_TIMEOUT_MS + 5_000);

  afterAll(() => {
    stop(running);
    rmSync(root, { recursive: true, force: true });
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

  it('GET /api/health on the LAN address is refused because the server does not bind 0.0.0.0', async () => {
    const lan = Object.values(networkInterfaces())
      .flat()
      .find((a) => a && a.family === 'IPv4' && !a.internal)?.address;
    // Positive control: loopback works on the same port right now.
    expect((await rawGet(running.port, '/api/health')).status).toBe(200);
    if (!lan) return; // host has no non-loopback IPv4; nothing to probe
    const accepted = await new Promise<boolean>((resolveConn) => {
      const socket = connect({ host: lan, port: running.port });
      socket.setTimeout(2000);
      socket.once('connect', () => {
        socket.destroy();
        resolveConn(true);
      });
      socket.once('error', () => resolveConn(false));
      socket.once('timeout', () => {
        socket.destroy();
        resolveConn(false);
      });
    });
    expect(accepted).toBe(false);
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
    root = mkdtempSync(join(tmpdir(), 'learn-trav-'));
    const app = join(root, 'app');
    mkdirSync(app, { recursive: true });
    cpSync(BUNDLE, join(app, 'server.js'));
    cpSync(join(LEARN_APP, 'dist'), join(app, 'dist'), { recursive: true });
    // Sits exactly where ../secret.txt from dist/ resolves, so an escape would succeed if the guard failed.
    writeFileSync(join(app, 'secret.txt'), SECRET);
    mkdirSync(join(root, 'project'));
    running = await startServer(join(app, 'server.js'), join(root, 'project'));
  }, SERVER_START_TIMEOUT_MS + 5_000);

  afterAll(() => {
    stop(running);
    rmSync(root, { recursive: true, force: true });
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

  it('lesson API with a valid id returns 501 named not_implemented', async () => {
    const res = await rawGet(running.port, '/api/lesson/intro-01');
    expect(res.status).toBe(501);
    expect(JSON.parse(res.body)).toEqual({ error: 'not_implemented' });
  });

  it.each(['/api/now', '/api/learner', '/api/tree', '/api/next'])(
    'stub route %s returns 501 named not_implemented',
    async (path) => {
      const res = await rawGet(running.port, path);
      expect(res.status).toBe(501);
      expect(JSON.parse(res.body)).toEqual({ error: 'not_implemented' });
    },
  );
});

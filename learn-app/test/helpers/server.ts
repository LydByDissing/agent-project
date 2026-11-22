// [origin ref=llm-dsl-p4o5,llm-dsl-gu1y.17,llm-dsl-2zv1.18 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Shared helpers to copy the seed learn/ tree (with fresh mtimes, as a git clone would produce) and to spawn the bundled server.js on a free port with a private home, always killed by PID when the test file ends.[/intent]
// [/origin]
import { spawn, type ChildProcess } from 'node:child_process';
import { cpSync, mkdirSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll } from 'vitest';
import { tmp } from './tmp.js';

const HERE = dirname(fileURLToPath(import.meta.url));
export const LEARN_APP = resolve(HERE, '..', '..');
export const REPO = resolve(LEARN_APP, '..');
export const FAKE = join(LEARN_APP, 'test', 'fixtures', 'fake-claude.mjs');
export const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

export function freePort(): Promise<number> {
  return new Promise((res, rej) => {
    const s = createServer();
    s.on('error', rej);
    s.listen(0, '127.0.0.1', () => {
      const p = (s.address() as { port: number }).port;
      s.close(() => res(p));
    });
  });
}

/** A second backend topic whose title differs from its slug, so "next lesson" has somewhere to go after a skip. */
export function addTlsTopic(project: string): void {
  const dir = join(project, 'learn', 'backend', 'tls-basics');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'index.yaml'), 'title: TLS basics\nsummary: Handshakes and certificates in one page.\n');
  writeFileSync(
    join(dir, '01-handshake.md'),
    [
      '---',
      'id: backend/tls-basics/01-handshake',
      'title: The TLS handshake',
      'level: intro',
      'requires: []',
      'sources:',
      '  - title: "RFC 8446 TLS 1.3"',
      '    url: https://www.rfc-editor.org/rfc/rfc8446',
      'updated: 2026-11-21',
      '---',
      '',
      'A TLS handshake agrees on keys before any application data is sent.',
      '',
    ].join('\n'),
  );
}

/**
 * Copies the repo seed learn/ into `project` with fresh mtimes; validation must not depend on them.
 * `domains` limits the copy to the named domain directories (e.g. ['backend']) so a test sees a fixed tree
 * even when the seed gains domains; omit it to copy the whole seed.
 */
export function copyLearn(project: string, opts: { tls?: boolean; domains?: string[] } = {}): void {
  if (opts.domains) {
    mkdirSync(join(project, 'learn'), { recursive: true });
    for (const domain of opts.domains) cpSync(join(REPO, 'learn', domain), join(project, 'learn', domain), { recursive: true });
  } else {
    cpSync(join(REPO, 'learn'), join(project, 'learn'), { recursive: true });
  }
  if (opts.tls) addTlsTopic(project);
}

export interface TmpProject {
  project: string;
  home: string;
}

/** A fresh project (seed learn/ copied, optional .sdd/now.json) and a private learner home. */
export function makeProject(opts: { tls?: boolean; now?: unknown; learner?: object | null; domains?: string[] } = {}): TmpProject {
  const project = tmp('learn-proj-');
  const home = tmp('learn-home-');
  copyLearn(project, { tls: opts.tls, domains: opts.domains });
  if (opts.now !== undefined) {
    mkdirSync(join(project, '.sdd'));
    writeFileSync(join(project, '.sdd', 'now.json'), JSON.stringify(opts.now));
  }
  if (opts.learner) writeFileSync(join(home, 'learner.json'), JSON.stringify(opts.learner));
  return { project, home };
}

export interface RunningServer {
  child: ChildProcess;
  base: string;
  port: number;
  stdout: () => string;
  stderr: () => string;
  stop: () => Promise<void>;
}

const running = new Set<RunningServer>();
afterAll(async () => {
  await Promise.all([...running].map((s) => s.stop()));
});

/**
 * Spawns `node <script> --project <project>` with SDD_LEARN_HOME always set to `home` (never the real ~/.sdd).
 * `port: undefined` picks a free port; `port: null` leaves SDD_LEARN_PORT unset (default-port test).
 */
export async function startLearnServer(opts: {
  project: string;
  home: string;
  script?: string;
  port?: number | null;
  env?: Record<string, string | undefined>;
  claude?: string | null;
  timeoutMs?: number;
}): Promise<RunningServer> {
  const port = opts.port === undefined ? await freePort() : opts.port;
  const env: Record<string, string | undefined> = { ...process.env, SDD_LEARN_HOME: opts.home, ...(opts.claude === null ? {} : { SDD_LEARN_CLAUDE: opts.claude ?? FAKE }), ...opts.env };
  if (port === null) delete env.SDD_LEARN_PORT;
  else env.SDD_LEARN_PORT = String(port);
  const child = spawn(process.execPath, [opts.script ?? join(LEARN_APP, 'server.js'), '--project', opts.project], {
    env: env as NodeJS.ProcessEnv,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stdout = '';
  let stderr = '';
  child.stdout!.on('data', (d: Buffer) => (stdout += d.toString()));
  child.stderr!.on('data', (d: Buffer) => (stderr += d.toString()));
  const exited = new Promise<void>((res) => child.once('exit', () => res()));
  const server: RunningServer = {
    child,
    base: `http://127.0.0.1:${port ?? 4747}`,
    port: port ?? 4747,
    stdout: () => stdout,
    stderr: () => stderr,
    stop: async () => {
      running.delete(server);
      if (child.exitCode === null && child.signalCode === null) child.kill('SIGTERM');
      await Promise.race([exited, sleep(3000)]);
      if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
    },
  };
  running.add(server);
  const end = Date.now() + (opts.timeoutMs ?? 10_000);
  while (!stdout.includes('listening')) {
    if (child.exitCode !== null) {
      await server.stop();
      throw new Error(`server exited ${child.exitCode}: ${stderr}`);
    }
    if (Date.now() > end) {
      await server.stop();
      throw new Error(`server did not start: ${stderr}`);
    }
    await sleep(20);
  }
  return server;
}

/** Sets or clears env vars around `fn` (restores the previous values afterwards). */
export async function withEnv<T>(env: Record<string, string>, fn: () => Promise<T>): Promise<T> {
  const saved: Record<string, string | undefined> = {};
  for (const k of Object.keys(env)) saved[k] = process.env[k];
  Object.assign(process.env, env);
  try {
    return await fn();
  } finally {
    for (const k of Object.keys(env)) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }
}

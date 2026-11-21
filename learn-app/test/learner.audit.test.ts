// [origin ref=llm-dsl-gu1y.6 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_server]
//   [intent]Audits learner.json locking and server start: stale locks are broken, fresh locks are respected, unknown schemas exit non-zero naming the version, and the project directory is never written.[/intent]
// [/origin]
import { spawnSync, type ChildProcess, spawn } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, statSync, unlinkSync, utimesSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { initLearner, readLearner, updateLearner } from '../src/state/learner.js';

const LEARN_APP = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = resolve(LEARN_APP, '..');
const tmp = (): string => mkdtempSync(join(tmpdir(), 'learn-audit-'));
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

function listTree(root: string): string[] {
  const out: string[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) walk(full);
      else out.push(relative(root, full));
    }
  };
  walk(root);
  return out.sort();
}

async function freePort(): Promise<number> {
  return new Promise((res) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => {
      const p = (s.address() as { port: number }).port;
      s.close(() => res(p));
    });
  });
}

async function startServer(project: string, home: string): Promise<{ base: string; stop: () => Promise<void> }> {
  const port = await freePort();
  const child: ChildProcess = spawn(process.execPath, [join(LEARN_APP, 'server.js'), '--project', project], {
    env: { ...process.env, SDD_LEARN_HOME: home, SDD_LEARN_PORT: String(port) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  await new Promise<void>((res, rej) => {
    child.stdout!.on('data', (d: Buffer) => d.toString().includes('listening') && res());
    child.on('exit', (c) => rej(new Error(`server exited ${c} before listening`)));
    setTimeout(() => rej(new Error('server start timeout')), 10_000);
  });
  return {
    base: `http://127.0.0.1:${port}`,
    stop: () =>
      new Promise((res) => {
        child.once('exit', () => res());
        child.kill();
      }),
  };
}

describe('learner.json lock staleness', () => {
  it('breaks a lock older than the stale timeout and the update succeeds', async () => {
    const home = tmp();
    await initLearner(home);
    const lock = join(home, 'learner.json.lock');
    writeFileSync(lock, '99999');
    const old = new Date(Date.now() - 60_000);
    utimesSync(lock, old, old);

    await updateLearner(home, (l) => ({ ...l, interest: { backend: 'deep' } }));

    expect(readLearner(home).interest).toEqual({ backend: 'deep' });
    expect(readdirSync(home)).toEqual(['learner.json']);
  }, 20_000);

  it('does not break a fresh lock held by another writer', async () => {
    const home = tmp();
    await initLearner(home);
    const lock = join(home, 'learner.json.lock');
    writeFileSync(lock, '99999');

    const pending = updateLearner(home, (l) => ({ ...l, interest: { backend: 'deep' } }));
    try {
      await sleep(300);
      expect(readFileSync(lock, 'utf8')).toBe('99999');
      expect(readLearner(home).interest).toEqual({});
    } finally {
      unlinkSync(lock);
    }
    await pending;

    expect(readLearner(home).interest).toEqual({ backend: 'deep' });
  }, 20_000);
});

describe('server start on learner.json', () => {
  it('exits non-zero and names the found schema version on stderr', () => {
    const home = tmp();
    writeFileSync(join(home, 'learner.json'), JSON.stringify({ schema: 9 }));
    const project = tmp();
    mkdirSync(join(project, 'learn'));

    const r = spawnSync(process.execPath, [join(LEARN_APP, 'server.js'), '--project', project], {
      env: { ...process.env, SDD_LEARN_HOME: home, SDD_LEARN_PORT: '0' },
      encoding: 'utf8',
      timeout: 10_000,
    });

    expect(r.status).toBe(1);
    expect(r.stderr).toContain('unsupported learner schema 9');
    expect(r.stdout).not.toContain('listening');
  });
});

describe('server writes only under SDD_LEARN_HOME', () => {
  it('leaves the project directory byte-for-byte unchanged across API requests', async () => {
    const project = tmp();
    cpSync(join(REPO, 'learn'), join(project, 'learn'), { recursive: true, preserveTimestamps: true });
    mkdirSync(join(project, '.sdd'));
    writeFileSync(join(project, '.sdd', 'now.json'), JSON.stringify({ jobs: [] }));
    const home = tmp();
    const before = listTree(project);

    const srv = await startServer(project, home);
    try {
      for (const p of ['/api/next', '/api/learner', '/api/tree', '/api/now']) {
        expect((await fetch(`${srv.base}${p}`)).status).toBe(200);
      }
    } finally {
      await srv.stop();
    }

    expect(before).toContain('.sdd/now.json');
    expect(listTree(project)).toEqual(before);
    expect(JSON.parse(readFileSync(join(home, 'learner.json'), 'utf8'))).toEqual({ schema: 1, interest: {}, mastery: {}, history: [] });
  }, 20_000);
});

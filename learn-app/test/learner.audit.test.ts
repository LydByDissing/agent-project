// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.6 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_server]
//   [intent]Audits learner.json locking and server start: stale locks are broken, fresh locks are respected, unknown schemas exit non-zero naming the version, and the project directory is never written.[/intent]
// [/origin]
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, unlinkSync, utimesSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { LEARN_APP, makeProject, sleep, startLearnServer } from './helpers/server.js';
import { tmp as tmpDir } from './helpers/tmp.js';
import { initLearner, readLearner, updateLearner } from '../src/state/learner.js';

const tmp = (): string => tmpDir('learn-audit-');

/** Maps every file under root to the sha256 of its contents, so "unchanged" means contents, not just names. */
function snapshot(root: string): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) walk(full);
      else out[relative(root, full)] = createHash('sha256').update(readFileSync(full)).digest('hex');
    }
  };
  walk(root);
  return out;
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
  it('exits 1, names the found schema version on stderr and leaves the file untouched', () => {
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
    expect(JSON.parse(readFileSync(join(home, 'learner.json'), 'utf8'))).toEqual({ schema: 9 });
  });
});

describe('server writes only under SDD_LEARN_HOME', () => {
  it('leaves every file of the project directory unchanged (same names, same content hashes) across API requests', async () => {
    const { project, home } = makeProject({ now: { jobs: [] } });
    const before = snapshot(project);

    const srv = await startLearnServer({ project, home, claude: null });
    for (const p of ['/api/next', '/api/learner', '/api/tree', '/api/now']) {
      expect((await fetch(`${srv.base}${p}`)).status).toBe(200);
    }
    await srv.stop();

    expect(Object.keys(before)).toContain('.sdd/now.json');
    expect(snapshot(project)).toEqual(before);
    expect(JSON.parse(readFileSync(join(home, 'learner.json'), 'utf8'))).toEqual({ schema: 1, interest: {}, mastery: {}, history: [] });
  }, 20_000);
});

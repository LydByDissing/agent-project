// [origin ref=llm-dsl-gu1y.5 req=REQ-OPERATOR-EDU-005 c4=learn_app/learn_server]
//   [intent]Verifies learner.json creation, schema refusal at server start, and that two concurrent processes lose no update.[/intent]
// [/origin]
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { beforeAll, describe, expect, it } from 'vitest';
import { UnsupportedSchemaError, emptyLearner, initLearner, learnHome, readLearner, updateLearner } from '../src/state/learner.js';

const LEARN_APP = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const tmp = (): string => mkdtempSync(join(tmpdir(), 'learn-state-'));

describe('learner state', () => {
  it('creates learner.json with schema 1 and empty sections when missing', async () => {
    const home = join(tmp(), 'nested');
    await initLearner(home);
    expect(JSON.parse(readFileSync(join(home, 'learner.json'), 'utf8'))).toEqual({ schema: 1, interest: {}, mastery: {}, history: [] });
    expect(readdirSync(home)).toEqual(['learner.json']);
  });

  it('does not overwrite an existing schema 1 file', async () => {
    const home = tmp();
    writeFileSync(join(home, 'learner.json'), JSON.stringify({ schema: 1, interest: { backend: 'deep' }, mastery: {}, history: [] }));
    await initLearner(home);
    expect(readLearner(home).interest).toEqual({ backend: 'deep' });
  });

  it('refuses an unknown schema, naming the version', async () => {
    const home = tmp();
    writeFileSync(join(home, 'learner.json'), JSON.stringify({ schema: 7 }));
    await expect(initLearner(home)).rejects.toThrow(UnsupportedSchemaError);
    await expect(initLearner(home)).rejects.toThrow(/schema 7/);
  });

  it('SDD_LEARN_HOME overrides ~/.sdd', () => {
    expect(learnHome({ SDD_LEARN_HOME: '/x/y' })).toBe('/x/y');
    expect(learnHome({})).toMatch(/\.sdd$/);
  });

  it('update re-reads, merges and leaves no temp or lock files', async () => {
    const home = tmp();
    await initLearner(home);
    await updateLearner(home, (l) => ({ ...l, interest: { ...l.interest, backend: 'deep' } }));
    await updateLearner(home, (l) => ({ ...l, mastery: { ...l.mastery, a: { box: 1, due: '2026-11-22' } } }));
    expect(readLearner(home)).toEqual({ ...emptyLearner(), interest: { backend: 'deep' }, mastery: { a: { box: 1, due: '2026-11-22' } } });
    expect(readdirSync(home)).toEqual(['learner.json']);
  });

  it('concurrent updates inside one process lose nothing', async () => {
    const home = tmp();
    await initLearner(home);
    await Promise.all(Array.from({ length: 20 }, (_, i) => updateLearner(home, (l) => ({ ...l, mastery: { ...l.mastery, [`k${i}`]: { box: 1, due: 'x' } } }))));
    expect(Object.keys(readLearner(home).mastery)).toHaveLength(20);
  });
});

describe('two writer processes', () => {
  let script: string;
  beforeAll(async () => {
    const dir = tmp();
    const entry = join(dir, 'writer.ts');
    writeFileSync(
      entry,
      `import { updateLearner } from ${JSON.stringify(join(LEARN_APP, 'src/state/learner.ts'))};
const [home, tag, n] = process.argv.slice(2);
for (let i = 0; i < Number(n); i++) {
  await updateLearner(home, (l) => ({ ...l, mastery: { ...l.mastery, [tag + i]: { box: 1, due: 'x' } } }));
}`,
    );
    script = join(dir, 'writer.mjs');
    await build({ entryPoints: [entry], bundle: true, platform: 'node', format: 'esm', outfile: script, logLevel: 'silent' });
  });

  it('both processes record every write', async () => {
    const home = tmp();
    mkdirSync(home, { recursive: true });
    const run = (tag: string): Promise<number> =>
      new Promise((res) => {
        const p = spawn(process.execPath, [script, home, tag, '40'], { stdio: 'inherit' });
        p.on('exit', (c) => res(c ?? 1));
      });
    const codes = await Promise.all([run('a'), run('b')]);
    expect(codes).toEqual([0, 0]);
    const keys = Object.keys(readLearner(home).mastery);
    expect(keys).toHaveLength(80);
    expect(readdirSync(home)).toEqual(['learner.json']);
  }, 30_000);
});

describe('server start with learner.json', () => {
  const project = (): string => {
    const p = tmp();
    mkdirSync(join(p, 'learn'));
    return p;
  };

  it('refuses to start on an unknown schema, naming the version, exit non-zero', () => {
    const home = tmp();
    writeFileSync(join(home, 'learner.json'), JSON.stringify({ schema: 9 }));
    const r = spawnSync(process.execPath, [join(LEARN_APP, 'server.js'), '--project', project()], {
      env: { ...process.env, SDD_LEARN_HOME: home, SDD_LEARN_PORT: '0' },
      encoding: 'utf8',
      timeout: 10_000,
    });
    expect(r.status).not.toBe(0);
    expect(r.status).not.toBeNull();
    expect(r.stderr).toContain('9');
    expect(existsSync(join(home, 'learner.json'))).toBe(true);
    expect(JSON.parse(readFileSync(join(home, 'learner.json'), 'utf8'))).toEqual({ schema: 9 });
  });
});

// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.7 req=REQ-OPERATOR-EDU-005 c4=learn_app/learn_server]
//   [intent]Verifies the stale-lock breaker never deletes a live lock created between its stat and its rename.[/intent]
// [/origin]
import { existsSync, readFileSync, readdirSync, renameSync, utimesSync, writeFileSync } from 'node:fs';
import { tmp as tmpDir } from './helpers/tmp.js';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { breakStaleLock } from '../src/state/learner.js';

function staleLock(): { dir: string; lock: string } {
  const dir = tmpDir('learn-lock-');
  const lock = join(dir, 'learner.json.lock');
  writeFileSync(lock, 'old');
  const old = new Date(Date.now() - 60_000);
  utimesSync(lock, old, old);
  return { dir, lock };
}

describe('breakStaleLock', () => {
  it('keeps a live lock that replaced the stale one between stat and rename', () => {
    const { dir, lock } = staleLock();
    const broken = breakStaleLock(lock, () => {
      writeFileSync(`${lock}.new`, 'live');
      renameSync(`${lock}.new`, lock);
    });
    expect(broken).toBe(false);
    expect(readFileSync(lock, 'utf8')).toBe('live');
    expect(readdirSync(dir)).toEqual(['learner.json.lock']);
  });
  it('breaks a genuinely stale lock and leaves no graveyard file', () => {
    const { dir, lock } = staleLock();
    expect(breakStaleLock(lock)).toBe(true);
    expect(existsSync(lock)).toBe(false);
    expect(readdirSync(dir)).toEqual([]);
  });
  it('leaves a fresh lock alone', () => {
    const dir = tmpDir('learn-lock-');
    const lock = join(dir, 'learner.json.lock');
    writeFileSync(lock, 'fresh');
    expect(breakStaleLock(lock)).toBe(false);
    expect(readFileSync(lock, 'utf8')).toBe('fresh');
  });
});

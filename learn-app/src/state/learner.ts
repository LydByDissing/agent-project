// [origin ref=llm-dsl-gu1y.5 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_server]
//   [intent]Owns ~/.sdd/learner.json: creates it, refuses unknown schemas, and applies updates under a lock with re-read, merge, temp write and rename.[/intent]
//   [inv]update() never loses a concurrent writer's change: read-modify-write runs only while holding learner.json.lock.[/inv]
// [/origin]
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, renameSync, statSync, unlinkSync, writeSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export type Interest = 'deep' | 'basics' | 'skip';

export interface Mastery {
  box: number;
  due: string;
}

export interface HistoryEntry {
  lesson: string;
  q: string;
  chosen: number;
  correct: number;
  at: string;
}

export interface Learner {
  schema: 1;
  interest: Record<string, Interest>;
  mastery: Record<string, Mastery>;
  history: HistoryEntry[];
}

export class UnsupportedSchemaError extends Error {
  constructor(readonly found: unknown, readonly file: string) {
    super(`${file}: unsupported learner schema ${JSON.stringify(found)} (this server understands schema 1)`);
    this.name = 'UnsupportedSchemaError';
  }
}

const LOCK_STALE_MS = 10_000;
const LOCK_TIMEOUT_MS = 15_000;
const LOCK_RETRY_MS = 5;

export function learnHome(env: NodeJS.ProcessEnv = process.env): string {
  return env.SDD_LEARN_HOME && env.SDD_LEARN_HOME !== '' ? env.SDD_LEARN_HOME : join(homedir(), '.sdd');
}

export function learnerFile(home: string): string {
  return join(home, 'learner.json');
}

export function emptyLearner(): Learner {
  return { schema: 1, interest: {}, mastery: {}, history: [] };
}

function parse(file: string): Learner {
  const raw = JSON.parse(readFileSync(file, 'utf8')) as Record<string, unknown>;
  if (raw === null || typeof raw !== 'object' || raw.schema !== 1) {
    throw new UnsupportedSchemaError((raw as { schema?: unknown } | null)?.schema, file);
  }
  const base = emptyLearner();
  return {
    schema: 1,
    interest: { ...base.interest, ...(raw.interest as Learner['interest']) },
    mastery: { ...base.mastery, ...(raw.mastery as Learner['mastery']) },
    history: Array.isArray(raw.history) ? (raw.history as HistoryEntry[]) : [],
  };
}

/** Reads the learner state; an absent file reads as an empty learner. */
export function readLearner(home: string): Learner {
  const file = learnerFile(home);
  return existsSync(file) ? parse(file) : emptyLearner();
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

async function withLock<T>(home: string, fn: () => T): Promise<T> {
  mkdirSync(home, { recursive: true });
  const lock = join(home, 'learner.json.lock');
  const started = Date.now();
  for (;;) {
    try {
      const fd = openSync(lock, 'wx');
      writeSync(fd, String(process.pid));
      closeSync(fd);
      break;
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== 'EEXIST') throw err;
      try {
        if (Date.now() - statSync(lock).mtimeMs > LOCK_STALE_MS) unlinkSync(lock);
      } catch {
        // lock vanished between checks; retry immediately
      }
      if (Date.now() - started > LOCK_TIMEOUT_MS) throw new Error(`timed out waiting for ${lock}`);
      await sleep(LOCK_RETRY_MS + Math.random() * 10);
    }
  }
  try {
    return fn();
  } finally {
    try {
      unlinkSync(lock);
    } catch {
      // already removed as stale
    }
  }
}

function writeAtomic(home: string, learner: Learner): void {
  const file = learnerFile(home);
  const tmp = join(home, `.learner.${process.pid}.${Date.now()}.tmp`);
  const fd = openSync(tmp, 'w');
  try {
    writeSync(fd, JSON.stringify(learner, null, 2) + '\n');
  } finally {
    closeSync(fd);
  }
  renameSync(tmp, file);
}

/** Creates learner.json when missing; throws UnsupportedSchemaError when it exists with another schema. */
export async function initLearner(home: string): Promise<Learner> {
  return withLock(home, () => {
    const file = learnerFile(home);
    if (existsSync(file)) return parse(file);
    const fresh = emptyLearner();
    writeAtomic(home, fresh);
    return fresh;
  });
}

/** Re-reads under the lock, applies fn to the fresh state, and writes the result atomically. */
export async function updateLearner(home: string, fn: (current: Learner) => Learner | void): Promise<Learner> {
  return withLock(home, () => {
    const current = readLearner(home);
    const next = fn(current) ?? current;
    writeAtomic(home, next);
    return next;
  });
}

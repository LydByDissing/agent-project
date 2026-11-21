// [origin ref=llm-dsl-gu1y.9 req=REQ-OPERATOR-EDU-006,REQ-OPERATOR-EDU-008 c4=learn_app/learn_server]
//   [intent]Checks that in-memory quizzes older than one hour are evicted on the next /api/quiz call (clock injected through AppOptions), and that an is_error claude envelope reports the CLI error text rather than a fake exit code.[/intent]
//   [inv]Quizzes are evicted only on /api/quiz calls; an envelope with is_error never produces an "exit 0" message.[/inv]
// [/origin]
import { chmodSync, cpSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { ClaudeExitError, parseQuiz, claudeOpts } from '../src/quiz/quiz.js';
import { createApp } from '../src/server/app.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const LEARN_APP = resolve(HERE, '..');
const REPO = resolve(LEARN_APP, '..');
const FAKE = join(HERE, 'fixtures', 'fake-claude.mjs');
const LESSON = 'backend/http-caching/01-freshness';
const HOUR = 60 * 60 * 1000;
const KEYS = ['s1'];
const tmp = (): string => mkdtempSync(join(tmpdir(), 'learn-quiz-expiry-'));

let savedEnv: Record<string, string | undefined> = {};
beforeAll(() => {
  savedEnv = { SDD_LEARN_HOME: process.env.SDD_LEARN_HOME, SDD_LEARN_CLAUDE: process.env.SDD_LEARN_CLAUDE };
  process.env.SDD_LEARN_HOME = tmp();
  process.env.SDD_LEARN_CLAUDE = FAKE;
  delete process.env.FAKE_CLAUDE_MODE;
});
afterAll(() => {
  for (const [k, v] of Object.entries(savedEnv)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
});

function stubBinary(stdout: string): string {
  const dir = tmp();
  const bin = join(dir, 'claude-stub.mjs');
  writeFileSync(bin, `#!${process.execPath}\nprocess.stdin.resume();\nprocess.stdin.on('end', () => process.stdout.write(${JSON.stringify(stdout)}));\n`);
  chmodSync(bin, 0o755);
  return bin;
}

function server(bin: string = FAKE) {
  const project = tmp();
  const home = tmp();
  cpSync(join(REPO, 'learn'), join(project, 'learn'), { recursive: true, preserveTimestamps: true });
  writeFileSync(join(home, 'learner.json'), JSON.stringify({ schema: 1, interest: { backend: 'deep' }, mastery: {}, history: [] }));
  let clock = Date.parse('2026-11-21T10:00:00Z');
  const app = createApp({
    project,
    distDir: project,
    home,
    today: () => '2026-11-21',
    now: () => clock,
    claude: () => ({ ...claudeOpts(), bin, timeoutMs: 10_000 }),
  });
  const post = (p: string, body?: unknown) =>
    app.request(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  return {
    post,
    advance: (ms: number) => (clock += ms),
    startQuiz: async (): Promise<string> => ((await (await post(`/api/quiz/${LESSON}`)).json()) as { quizId: string }).quizId,
    answer: (quizId: string) => post('/api/answer', { quizId, questionIndex: 0, chosen: 0 }),
  };
}

describe('quiz expiry', () => {
  it('a quiz generated 59 minutes ago is still answerable (positive control)', async () => {
    const s = server();
    const a = await s.startQuiz();
    s.advance(HOUR - 60_000);
    await s.startQuiz();
    expect((await s.answer(a)).status).toBe(200);
  });

  it('a quiz older than one hour is evicted on the next /api/quiz call and answering it is 404', async () => {
    const s = server();
    const a = await s.startQuiz();
    s.advance(HOUR + 60_000);
    const b = await s.startQuiz();
    const gone = await s.answer(a);
    expect(gone.status).toBe(404);
    expect(((await gone.json()) as { error: string }).error).toBe('unknown_quiz');
    expect((await s.answer(b)).status).toBe(200);
  });

  it('a stale quiz is not evicted by an /api/answer call alone', async () => {
    const s = server();
    const a = await s.startQuiz();
    s.advance(HOUR + 60_000);
    expect((await s.answer(a)).status).toBe(200);
  });
});

describe('claude envelope with is_error', () => {
  it('parseQuiz names the CLI error and carries its result text, not "exit 0"', () => {
    const stdout = JSON.stringify({ type: 'result', is_error: true, result: 'Credit balance too low' });
    let err: unknown;
    try {
      parseQuiz(stdout, KEYS);
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ClaudeExitError);
    const msg = (err as Error).message;
    expect(msg).toContain('reported an error');
    expect(msg).toContain('Credit balance too low');
    expect(msg).not.toContain('exit 0');
  });

  it('falls back to the envelope subtype when there is no result text', () => {
    const stdout = JSON.stringify({ type: 'result', is_error: true, subtype: 'error_max_turns' });
    expect(() => parseQuiz(stdout, KEYS)).toThrow(/reported an error.*error_max_turns/);
  });

  it('positive control: a non-zero exit still reports its real exit code', async () => {
    const s = server();
    const res = await withEnv({ FAKE_CLAUDE_MODE: 'exit' }, () => s.post(`/api/quiz/${LESSON}`));
    const body = (await res.json()) as { error: { name: string; message: string } };
    expect(res.status).toBe(502);
    expect(body.error.name).toBe('ClaudeExitError');
    expect(body.error.message).toContain('failed (exit 3)');
  });

  it('the API answers 502 with the CLI error text for an is_error envelope', async () => {
    const s = server(stubBinary(JSON.stringify({ type: 'result', is_error: true, result: 'Not logged in' })));
    const res = await s.post(`/api/quiz/${LESSON}`);
    const body = (await res.json()) as { error: { name: string; message: string }; questions?: unknown };
    expect(res.status).toBe(502);
    expect(body.error.name).toBe('ClaudeExitError');
    expect(body.error.message).toContain('reported an error');
    expect(body.error.message).toContain('Not logged in');
    expect(body.error.message).not.toContain('exit 0');
    expect(body).not.toHaveProperty('questions');
  });
});

async function withEnv<T>(env: Record<string, string>, fn: () => Promise<T>): Promise<T> {
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

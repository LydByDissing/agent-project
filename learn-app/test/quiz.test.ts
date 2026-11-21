// [origin ref=llm-dsl-gu1y.7 req=REQ-OPERATOR-EDU-008,REQ-OPERATOR-EDU-009 c4=learn_app/question_generator]
//   [intent]Tests prompt building, claude -p invocation via a fake script, strict validation errors, server grading and Leitner transitions with injected today.[/intent]
// [/origin]
import { cpSync, existsSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  ClaudeExitError, ClaudeMissingError, ClaudeTimeoutError, QuizSchemaError, UnknownSourceError,
  buildPrompt, generateQuiz, parseQuiz, runClaude,
} from '../src/quiz/quiz.js';
import { createApp } from '../src/server/app.js';
import { leitner } from '../src/state/leitner.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const FAKE = join(HERE, 'fixtures', 'fake-claude.mjs');
const LESSON = 'backend/http-caching/01-freshness';
const tmp = (): string => mkdtempSync(join(tmpdir(), 'learn-quiz-'));

const lesson = { id: 'x/y/01-z', title: 'T', body: 'BODY TEXT', sources: [{ title: 'RFC', url: 'https://e.org/rfc' }, { title: 'Repo', path: 'a.ts', line: 3 }] };

async function withMode<T>(mode: string, fn: () => Promise<T>, extra: Record<string, string> = {}): Promise<T> {
  const saved = { ...process.env };
  Object.assign(process.env, { SDD_LEARN_CLAUDE: FAKE, FAKE_CLAUDE_MODE: mode }, extra);
  try {
    return await fn();
  } finally {
    for (const k of ['SDD_LEARN_CLAUDE', 'FAKE_CLAUDE_MODE', ...Object.keys(extra)]) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }
}
const slice = { box: 2, interest: 'deep', misses: [] as string[] };
const gen = (mode: string, extra?: Record<string, string>) => withMode(mode, () => generateQuiz(lesson, slice, { timeoutMs: 5000 }), extra);

describe('buildPrompt', () => {
  it('contains body, source keys, box, interest and past-miss summaries', () => {
    const p = buildPrompt(lesson, { box: 4, interest: 'basics', misses: ['no-cache vs no-store', 'ETag basics'] });
    expect(p).toContain('BODY TEXT');
    expect(p).toContain('s1: RFC (https://e.org/rfc)');
    expect(p).toContain('s2: Repo (a.ts:3)');
    expect(p).toContain('box 4');
    expect(p).toContain('basics');
    expect(p).toContain('- no-cache vs no-store');
    expect(p).toContain('- ETag basics');
  });
  it('states when there are no misses', () => {
    expect(buildPrompt(lesson, slice)).toContain('none recorded');
  });
});

describe('generateQuiz via fake claude', () => {
  it('parses valid output and passes -p --output-format json with the prompt on stdin', async () => {
    const dir = tmp();
    const log = join(dir, 'argv.log');
    const pf = join(dir, 'prompt.txt');
    const qs = await gen('valid', { FAKE_CLAUDE_LOG: log, FAKE_CLAUDE_PROMPT_FILE: pf });
    expect(qs).toHaveLength(3);
    expect(qs[0].options).toHaveLength(3);
    expect(JSON.parse(readFileSync(log, 'utf8').trim())).toEqual(['-p', '--output-format', 'json', '--no-session-persistence']);
    expect(readFileSync(pf, 'utf8')).toContain('BODY TEXT');
  });
  it('tolerates a ```json fence', async () => {
    expect(await gen('fenced')).toHaveLength(3);
  });
  it('rejects the wrong question count', async () => {
    await expect(gen('wrong-count')).rejects.toThrow(QuizSchemaError);
    await expect(gen('wrong-count')).rejects.toThrow(/exactly 3 questions, got 2/);
  });
  it('rejects two correct indices', async () => {
    await expect(gen('two-correct')).rejects.toThrow(/questions\[1\]\.correct/);
  });
  it('rejects an unknown source and names the key', async () => {
    const err = await gen('unknown-source').catch((e) => e);
    expect(err).toBeInstanceOf(UnknownSourceError);
    expect(err.message).toContain('s99');
  });
  it('reports non-zero exit with code and stderr', async () => {
    const err = await gen('exit').catch((e) => e);
    expect(err).toBeInstanceOf(ClaudeExitError);
    expect(err.code).toBe(3);
    expect(err.message).toContain('not logged in');
  });
  it('times out', async () => {
    const t = Date.now();
    await expect(withMode('sleep', () => runClaude('p', { timeoutMs: 300 }))).rejects.toThrow(ClaudeTimeoutError);
    expect(Date.now() - t).toBeLessThan(5000);
  });
  it('names a missing binary', async () => {
    const err = await runClaude('p', { bin: '/nonexistent/claude-xyz' }).catch((e) => e);
    expect(err).toBeInstanceOf(ClaudeMissingError);
    expect(err.message).toContain('/nonexistent/claude-xyz');
  });
  it('rejects non-JSON stdout', async () => {
    await expect(gen('garbage')).rejects.toThrow(QuizSchemaError);
  });
});

describe('parseQuiz strictness', () => {
  const env = (obj: unknown): string => JSON.stringify({ result: JSON.stringify(obj) });
  const q = (o: object = {}) => ({ q: 'a?', options: [1, 2, 3].map((n) => ({ text: `t${n}`, explanation: `e${n}` })), correct: 0, source: 's1', ...o });
  it('rejects 2 and 6 options, out-of-range and fractional correct, missing explanation', () => {
    const bad = [
      q({ options: q().options.slice(0, 2) }),
      q({ options: [...q().options, ...q().options] }),
      q({ correct: 3 }),
      q({ correct: 0.5 }),
      q({ options: [{ text: 'a', explanation: 'x' }, { text: 'b' }, { text: 'c', explanation: 'y' }] }),
    ];
    for (const b of bad) expect(() => parseQuiz(env({ questions: [b, q(), q()] }), ['s1'])).toThrow(QuizSchemaError);
  });
  it('accepts 5 options', () => {
    const five = q({ options: [1, 2, 3, 4, 5].map((n) => ({ text: `t${n}`, explanation: `e${n}` })), correct: 4 });
    expect(parseQuiz(env({ questions: [five, q(), q()] }), ['s1'])[0].correct).toBe(4);
  });
});

describe('leitner', () => {
  it('moves up one box on all-correct, caps at 5, drops to 1 on any wrong', () => {
    expect(leitner(2, true, '2026-11-21')).toEqual({ box: 3, due: '2026-11-25' });
    expect(leitner(5, true, '2026-11-21')).toEqual({ box: 5, due: '2026-12-07' });
    expect(leitner(4, false, '2026-11-30')).toEqual({ box: 1, due: '2026-12-01' });
    expect(leitner(0, true, '2026-11-21')).toEqual({ box: 1, due: '2026-11-22' });
  });
  it('rejects a malformed today', () => {
    expect(() => leitner(1, true, 'tomorrow')).toThrow(/YYYY-MM-DD/);
  });
});

function server(learner: object) {
  const project = tmp();
  const home = tmp();
  cpSync(join(REPO, 'learn'), join(project, 'learn'), { recursive: true });
  writeFileSync(join(home, 'learner.json'), JSON.stringify({ schema: 1, interest: { backend: 'deep' }, mastery: {}, history: [], ...learner }));
  const app = createApp({ project, distDir: project, home, today: () => '2026-11-21' });
  const post = (p: string, body?: unknown) =>
    app.request(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const state = () => JSON.parse(readFileSync(join(home, 'learner.json'), 'utf8'));
  return { app, post, state, home };
}

// fake quiz: every question's correct index is 1
async function startQuiz(s: ReturnType<typeof server>, mode = 'valid', extra?: Record<string, string>) {
  const res = await withMode(mode, () => s.post(`/api/quiz/${LESSON}`), extra);
  return { res, body: (await res.json()) as any };
}

describe('POST /api/quiz and /api/answer', () => {
  it('returns questions without correct indices or explanations', async () => {
    const s = server({});
    const { res, body } = await startQuiz(s);
    expect(res.status).toBe(200);
    expect(body.questions).toHaveLength(3);
    expect(JSON.stringify(body)).not.toMatch(/correct|Because/);
    expect(body.persona.box).toBe(0);
  });
  it('passes box, interest and two past misses into the prompt', async () => {
    const pf = join(tmp(), 'p.txt');
    const at = '2026-11-01T00:00:00Z';
    const s = server({
      mastery: { [LESSON]: { box: 2, due: '2026-11-20' } },
      history: [
        { lesson: LESSON, q: 'no-cache vs no-store', chosen: 0, correct: 1, at },
        { lesson: LESSON, q: 'max-age vs s-maxage', chosen: 2, correct: 0, at },
        { lesson: LESSON, q: 'already right', chosen: 1, correct: 1, at },
        { lesson: 'other/lesson/01-x', q: 'other miss', chosen: 0, correct: 1, at },
      ],
    });
    const { body } = await startQuiz(s, 'valid', { FAKE_CLAUDE_PROMPT_FILE: pf });
    const prompt = readFileSync(pf, 'utf8');
    expect(prompt).toContain('box 2');
    expect(prompt).toContain('deep');
    expect(prompt).toContain('no-cache vs no-store');
    expect(prompt).toContain('max-age vs s-maxage');
    expect(prompt).not.toContain('other miss');
    expect(prompt).not.toContain('already right');
    expect(body.persona.misses).toHaveLength(2);
  });
  it.each([
    ['wrong-count', 502, 'QuizSchemaError'],
    ['unknown-source', 502, 'UnknownSourceError'],
    ['exit', 502, 'ClaudeExitError'],
  ])('maps %s to %i %s and never returns questions', async (mode, status, name) => {
    const { res, body } = await startQuiz(server({}), mode);
    expect(res.status).toBe(status);
    expect(body.error.name).toBe(name);
    expect(body.questions).toBeUndefined();
  });
  it('maps timeout to 504 and a missing binary to 502 naming it', async () => {
    const s = server({});
    const t = await startQuiz(s, 'sleep', { SDD_LEARN_QUIZ_TIMEOUT_S: '0.3' });
    expect(t.res.status).toBe(504);
    expect(t.body.error.name).toBe('ClaudeTimeoutError');
    const m = await startQuiz(s, 'valid', { SDD_LEARN_CLAUDE: '/nonexistent/claude-xyz' });
    expect(m.res.status).toBe(502);
    expect(m.body.error.name).toBe('ClaudeMissingError');
    expect(m.body.error.message).toContain('/nonexistent/claude-xyz');
  });
  it('404s an unknown lesson', async () => {
    const s = server({});
    expect((await withMode('valid', () => s.post('/api/quiz/backend/nope/01-x'))).status).toBe(404);
  });

  const answerAll = async (s: ReturnType<typeof server>, picks: number[]) => {
    const { body } = await startQuiz(s);
    const outs = [];
    for (const [i, c] of picks.entries()) outs.push(await (await s.post('/api/answer', { quizId: body.quizId, questionIndex: i, chosen: c })).json() as any);
    return outs;
  };

  it('box 2 all correct -> box 3 due today+4, history appended with explanation and source', async () => {
    const s = server({ mastery: { [LESSON]: { box: 2, due: '2026-11-20' } } });
    const outs = await answerAll(s, [1, 1, 1]);
    expect(outs[0]).toMatchObject({ correct: true, complete: false, correctIndex: 1 });
    expect(outs[0].explanations).toEqual(['Because 0', 'Because 1', 'Because 2']);
    expect(outs[0].source).toMatchObject({ key: 's1' });
    expect(outs[2]).toMatchObject({ complete: true, allCorrect: true, box: 3, due: '2026-11-25' });
    const st = s.state();
    expect(st.mastery[LESSON]).toEqual({ box: 3, due: '2026-11-25' });
    expect(st.history).toHaveLength(3);
    expect(st.history[0]).toMatchObject({ lesson: LESSON, chosen: 1, correct: 1, explanation: 'Because 1', source: 's1' });
    expect(typeof st.history[0].at).toBe('string');
  });
  it('any wrong -> box 1 due tomorrow', async () => {
    const s = server({ mastery: { [LESSON]: { box: 4, due: '2026-11-20' } } });
    const outs = await answerAll(s, [1, 0, 1]);
    expect(outs[1].correct).toBe(false);
    expect(outs[2]).toMatchObject({ complete: true, allCorrect: false, box: 1, due: '2026-11-22' });
    expect(s.state().mastery[LESSON]).toEqual({ box: 1, due: '2026-11-22' });
  });
  it('box 5 all correct stays 5', async () => {
    const s = server({ mastery: { [LESSON]: { box: 5, due: '2026-11-20' } } });
    const outs = await answerAll(s, [1, 1, 1]);
    expect(outs[2]).toMatchObject({ box: 5, due: '2026-12-07' });
  });
  it('does not change mastery until all questions are answered', async () => {
    const s = server({ mastery: { [LESSON]: { box: 2, due: '2026-11-20' } } });
    await answerAll(s, [1, 1]);
    expect(s.state().mastery[LESSON]).toEqual({ box: 2, due: '2026-11-20' });
    expect(s.state().history).toHaveLength(2);
  });
  it('rejects bad input and double answers; unknown quiz is 404', async () => {
    const s = server({});
    const { body } = await startQuiz(s);
    const a = (o: object) => s.post('/api/answer', { quizId: body.quizId, ...o });
    expect((await a({ questionIndex: 5, chosen: 0 })).status).toBe(400);
    expect((await a({ questionIndex: 0, chosen: 9 })).status).toBe(400);
    expect((await a({ questionIndex: 0, chosen: 'x' })).status).toBe(400);
    expect((await a({ questionIndex: 0, chosen: 1 })).status).toBe(200);
    expect((await a({ questionIndex: 0, chosen: 1 })).status).toBe(409);
    expect((await s.post('/api/answer', { quizId: 'nope', questionIndex: 0, chosen: 0 })).status).toBe(404);
    expect(s.state().history).toHaveLength(1);
  });
  it('leaves no stale lock or temp files in home', async () => {
    const s = server({});
    await answerAll(s, [1, 1, 1]);
    expect(readdirSync(s.home).filter((f) => f.includes('lock') || f.endsWith('.tmp'))).toEqual([]);
    expect(existsSync(join(s.home, 'learner.json'))).toBe(true);
  });
});

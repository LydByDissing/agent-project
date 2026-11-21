// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.8 req=REQ-OPERATOR-EDU-008,REQ-OPERATOR-EDU-009 c4=learn_app/question_generator]
//   [intent]Audits the t4 quiz acceptance criterion: the payload never leaks answers, grading is server-side, Leitner boxes follow the 0/1/2/4/8/16 table across year rollover, the prompt is lesson-scoped, validation rejects malformed quizzes, and the bundle wires the quiz with Retry.[/intent]
// [/origin]
import { existsSync, readFileSync, readdirSync, utimesSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import {
  ClaudeMissingError, QuizSchemaError, UnknownSourceError,
  buildPrompt, claudeOpts, generateQuiz, parseQuiz,
} from '../src/quiz/quiz.js';
import { INTERVAL_DAYS, leitner } from '../src/state/leitner.js';
import { FAKE, LEARN_APP, copyLearn, startLearnServer, withEnv } from './helpers/server.js';
import { LESSON, OTHER, quizServer, type QuizServer as Server } from './helpers/quiz.js';
import { tmp } from './helpers/tmp.js';

const server = (learner: Record<string, unknown> = {}, today?: string): Server => quizServer(learner, { today });

// Every test runs with a private SDD_LEARN_HOME and the fake CLI; the real `claude` must never be spawned.
let savedEnv: Record<string, string | undefined> = {};
beforeAll(() => {
  savedEnv = { SDD_LEARN_HOME: process.env.SDD_LEARN_HOME, SDD_LEARN_CLAUDE: process.env.SDD_LEARN_CLAUDE, SDD_LEARN_QUIZ_TIMEOUT_S: process.env.SDD_LEARN_QUIZ_TIMEOUT_S };
  process.env.SDD_LEARN_HOME = tmp();
});
beforeEach(() => {
  process.env.SDD_LEARN_CLAUDE = FAKE;
  delete process.env.SDD_LEARN_QUIZ_TIMEOUT_S;
  delete process.env.FAKE_CLAUDE_MODE;
});
afterAll(() => {
  for (const [k, v] of Object.entries(savedEnv)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
});

/** Starts a quiz for a lesson with the fake claude in valid mode unless `env` overrides it. */
async function startQuiz(s: Server, env: Record<string, string> = {}, lesson = LESSON) {
  const res = await withEnv({ FAKE_CLAUDE_MODE: 'valid', ...env }, () => s.post(`/api/quiz/${lesson}`));
  const body = (await res.json()) as any;
  return { res, body };
}

async function answer(s: Server, quizId: string, questionIndex: unknown, chosen: unknown, extra: object = {}) {
  const res = await s.post('/api/answer', { quizId, questionIndex, chosen, ...extra });
  return { res, body: (await res.json()) as any };
}

/** The fake quiz has correct index 1 for every question. */
async function answerAll(s: Server, picks: number[]) {
  const { body } = await startQuiz(s);
  const outs: any[] = [];
  for (const [i, c] of picks.entries()) outs.push((await answer(s, body.quizId, i, c)).body);
  return outs;
}

function keysDeep(v: unknown, out: string[] = []): string[] {
  if (Array.isArray(v)) v.forEach((x) => keysDeep(x, out));
  else if (v !== null && typeof v === 'object') {
    for (const [k, x] of Object.entries(v)) {
      out.push(k);
      keysDeep(x, out);
    }
  }
  return out;
}

const envelope = (payload: unknown): string => JSON.stringify({ type: 'result', is_error: false, result: JSON.stringify(payload) });
const option = (n: number) => ({ text: `t${n}`, explanation: `e${n}` });
const question = (over: object = {}) => ({ q: 'What?', options: [option(0), option(1), option(2)], correct: 0, source: 's1', ...over });
const KEYS = ['s1', 's2'];

describe('quiz payload sent to the client', () => {
  it('contains no correct, correctIndex, explanation, explanations, source or sources key at any depth', async () => {
    const s = server();
    const { body } = await startQuiz(s);
    const forbidden = ['correct', 'correctIndex', 'explanation', 'explanations', 'source', 'sources'];
    const leaked = keysDeep(body).filter((k) => forbidden.includes(k));
    expect(leaked, `quiz payload leaked keys: ${leaked.join(', ')}`).toEqual([]);
  });
  it('lists options as plain strings so explanations cannot be read from the payload', async () => {
    const { body } = await startQuiz(server());
    for (const q of body.questions) {
      for (const o of q.options) expect(typeof o, `option ${JSON.stringify(o)} is not a string`).toBe('string');
    }
  });
  it('contains none of the explanation text the fake CLI produced', async () => {
    const { body } = await startQuiz(server());
    expect(JSON.stringify(body)).not.toContain('Because');
  });
});

describe('server-side grading of POST /api/answer', () => {
  it('ignores client-supplied correct, allCorrect and box fields and grades from the stored quiz', async () => {
    const s = server({ mastery: { [LESSON]: { box: 2, due: '2026-11-20' } } });
    const { body } = await startQuiz(s);
    const cheat = { correct: true, allCorrect: true, box: 5 };
    const first = await answer(s, body.quizId, 0, 0, cheat);
    expect(first.body.correct, 'client claimed correct=true; server must grade chosen 0 against correct 1').toBe(false);
    expect(first.body.correctIndex).toBe(1);
    await answer(s, body.quizId, 1, 1, cheat);
    const last = await answer(s, body.quizId, 2, 1, cheat);
    expect(last.body).toMatchObject({ complete: true, allCorrect: false, box: 1 });
    expect(s.state().mastery[LESSON]).toEqual({ box: 1, due: '2026-11-22' });
    expect(s.state().history[0]).toMatchObject({ chosen: 0, correct: 1 });
  });
  it('answering the same question twice returns 409 and keeps the first recorded choice', async () => {
    const s = server();
    const { body } = await startQuiz(s);
    expect((await answer(s, body.quizId, 0, 0)).res.status).toBe(200);
    const again = await answer(s, body.quizId, 0, 1);
    expect(again.res.status).toBe(409);
    expect(s.state().history).toHaveLength(1);
    expect(s.state().history[0].chosen, 'second answer overwrote the first').toBe(0);
  });
  it('an unknown quizId returns 404', async () => {
    const s = server();
    const res = await s.post('/api/answer', { quizId: randomUUID(), questionIndex: 0, chosen: 0 });
    expect(res.status).toBe(404);
    expect(s.state().history).toHaveLength(0);
  });
  it.each([
    ['negative', -1],
    ['equal to option count', 3],
    ['fractional', 1.5],
    ['string', '1'],
    ['null', null],
  ])('a %s chosen index returns 400 and writes nothing', async (_label, chosen) => {
    const s = server();
    const { body } = await startQuiz(s);
    const { res } = await answer(s, body.quizId, 0, chosen);
    expect(res.status).toBe(400);
    expect(s.state().history).toHaveLength(0);
  });
  it.each([
    ['past the last question', 3],
    ['negative', -1],
    ['fractional', 0.5],
    ['string', '0'],
  ])('a %s questionIndex returns 400', async (_label, idx) => {
    const s = server();
    const { body } = await startQuiz(s);
    expect((await answer(s, body.quizId, idx, 0)).res.status).toBe(400);
  });
  it('a rejected answer does not consume the question', async () => {
    const s = server();
    const { body } = await startQuiz(s);
    expect((await answer(s, body.quizId, 0, 9)).res.status).toBe(400);
    expect((await answer(s, body.quizId, 0, 1)).res.status).toBe(200);
  });
  it('an answer stores the explanation and source of the chosen option', async () => {
    const s = server();
    const { body } = await startQuiz(s);
    await answer(s, body.quizId, 0, 2);
    expect(s.state().history[0]).toMatchObject({ chosen: 2, correct: 1, explanation: 'Because 2', source: 's1' });
  });
});

describe('Leitner transitions', () => {
  // Hard-coded expected table: boxes 0..5 with all-correct and today 2026-11-21.
  it.each([
    [0, 1, '2026-11-22'],
    [1, 2, '2026-11-23'],
    [2, 3, '2026-11-25'],
    [3, 4, '2026-11-29'],
    [4, 5, '2026-12-07'],
    [5, 5, '2026-12-07'],
  ])('box %i all correct moves to box %i due %s', (box, next, due) => {
    expect(leitner(box, true, '2026-11-21')).toEqual({ box: next, due });
  });
  it('the interval table is exactly 0, 1, 2, 4, 8, 16 days', () => {
    expect([...INTERVAL_DAYS]).toEqual([0, 1, 2, 4, 8, 16]);
  });
  it('year rollover: box 2 all correct on 2026-12-30 is due 2027-01-03', () => {
    expect(leitner(2, true, '2026-12-30')).toEqual({ box: 3, due: '2027-01-03' });
  });
  it.each([
    [0, 1, '2026-12-31'],
    [1, 2, '2027-01-01'],
    [2, 3, '2027-01-03'],
    [3, 4, '2027-01-07'],
    [4, 5, '2027-01-15'],
    [5, 5, '2027-01-15'],
  ])('through the server, box %i all correct on 2026-12-30 gives box %i due %s', async (box, next, due) => {
    const s = server({ mastery: { [LESSON]: { box, due: '2026-12-01' } } }, '2026-12-30');
    const outs = await answerAll(s, [1, 1, 1]);
    expect(outs[2]).toMatchObject({ complete: true, allCorrect: true, box: next, due });
    expect(s.state().mastery[LESSON]).toEqual({ box: next, due });
  });
  it('a wrong answer from box 4 drops to box 1 due tomorrow across the year boundary', async () => {
    const s = server({ mastery: { [LESSON]: { box: 4, due: '2026-12-01' } } }, '2026-12-31');
    const outs = await answerAll(s, [1, 1, 0]);
    expect(outs[2]).toMatchObject({ allCorrect: false, box: 1, due: '2027-01-01' });
  });
  it('a wrong answer from box 5 drops to box 1 due tomorrow', async () => {
    const s = server({ mastery: { [LESSON]: { box: 5, due: '2026-12-01' } } });
    const outs = await answerAll(s, [0, 1, 1]);
    expect(outs[2]).toMatchObject({ box: 1, due: '2026-11-22' });
  });
  it('mastery stays unchanged while questions remain, even after wrong answers', async () => {
    const s = server({ mastery: { [LESSON]: { box: 4, due: '2026-11-20' } } });
    const { body } = await startQuiz(s);
    await answer(s, body.quizId, 0, 0);
    await answer(s, body.quizId, 1, 0);
    expect(s.state().mastery[LESSON]).toEqual({ box: 4, due: '2026-11-20' });
    await answer(s, body.quizId, 2, 1);
    expect(s.state().mastery[LESSON]).toEqual({ box: 1, due: '2026-11-22' });
  });
});

describe('prompt personalisation', () => {
  const lesson = { id: 'x/y/01-z', title: 'T', body: 'BODY', sources: [{ title: 'RFC', url: 'https://e.org' }] };

  it('lists past misses for this lesson only, not misses from other lessons', async () => {
    const s = server({
      history: [
        { lesson: LESSON, q: 'this lesson miss', chosen: 0, correct: 1, at: '2026-11-01T00:00:00Z' },
        { lesson: OTHER, q: 'other lesson miss', chosen: 0, correct: 1, at: '2026-11-01T00:00:00Z' },
      ],
    });
    const pf = join(tmp(), 'prompt.txt');
    const { body } = await startQuiz(s, { FAKE_CLAUDE_PROMPT_FILE: pf });
    const prompt = readFileSync(pf, 'utf8');
    expect(prompt).toContain('- this lesson miss');
    expect(prompt).not.toContain('other lesson miss');
    expect(body.persona.misses).toEqual(['this lesson miss']);
  });
  it('says none recorded when only other lessons have misses', async () => {
    const s = server({
      history: [{ lesson: OTHER, q: 'other lesson miss', chosen: 0, correct: 1, at: '2026-11-01T00:00:00Z' }],
    });
    const pf = join(tmp(), 'prompt.txt');
    await startQuiz(s, { FAKE_CLAUDE_PROMPT_FILE: pf });
    expect(readFileSync(pf, 'utf8')).toContain('none recorded');
  });
  it('carries box 0 for an unseen lesson and the learner interest for its topic', async () => {
    const s = server({ interest: { backend: 'basics' } });
    const pf = join(tmp(), 'prompt.txt');
    await startQuiz(s, { FAKE_CLAUDE_PROMPT_FILE: pf });
    const prompt = readFileSync(pf, 'utf8');
    expect(prompt).toContain('Leitner box 0 of 5');
    expect(prompt).toContain('Interest level in this subject: basics');
  });
  it('buildPrompt puts the box and interest of the given learner slice into the text', () => {
    const p = buildPrompt(lesson, { box: 3, interest: 'deep', misses: [] });
    expect(p).toContain('Leitner box 3 of 5');
    expect(p).toContain('Interest level in this subject: deep');
  });
});

describe('quiz validation (parseQuiz)', () => {
  it('rejects a 2-question payload and names the count', () => {
    expect(() => parseQuiz(envelope({ questions: [question(), question()] }), KEYS)).toThrow(/exactly 3 questions, got 2/);
  });
  it('rejects a 4-question payload and names the count', () => {
    expect(() => parseQuiz(envelope({ questions: [question(), question(), question(), question()] }), KEYS)).toThrow(/exactly 3 questions, got 4/);
  });
  it('rejects a question with 2 options', () => {
    const q = question({ options: [option(0), option(1)] });
    expect(() => parseQuiz(envelope({ questions: [q, question(), question()] }), KEYS)).toThrow(QuizSchemaError);
  });
  it('rejects a question with 6 options', () => {
    const q = question({ options: [0, 1, 2, 3, 4, 5].map(option) });
    expect(() => parseQuiz(envelope({ questions: [q, question(), question()] }), KEYS)).toThrow(QuizSchemaError);
  });
  it('rejects a correct index given as a string', () => {
    const q = question({ correct: '1' });
    expect(() => parseQuiz(envelope({ questions: [q, question(), question()] }), KEYS)).toThrow(/correct must be a single integer/);
  });
  it('rejects a fractional correct index', () => {
    const q = question({ correct: 1.5 });
    expect(() => parseQuiz(envelope({ questions: [q, question(), question()] }), KEYS)).toThrow(QuizSchemaError);
  });
  it('rejects a correct index equal to the option count', () => {
    const q = question({ correct: 3 });
    expect(() => parseQuiz(envelope({ questions: [q, question(), question()] }), KEYS)).toThrow(QuizSchemaError);
  });
  it('rejects a payload where one option has no explanation', () => {
    const q = question({ options: [option(0), { text: 't1' }, option(2)] });
    expect(() => parseQuiz(envelope({ questions: [q, question(), question()] }), KEYS)).toThrow(/options\[1\] needs non-empty text and explanation/);
  });
  it('rejects a source key that is not among the lesson sources', () => {
    const q = question({ source: 's3' });
    expect(() => parseQuiz(envelope({ questions: [q, question(), question()] }), KEYS)).toThrow(UnknownSourceError);
  });
  it('rejects a question with no source key', () => {
    const { source: _omit, ...q } = question();
    expect(() => parseQuiz(envelope({ questions: [q, question(), question()] }), KEYS)).toThrow(QuizSchemaError);
  });
  it('accepts a payload wrapped in a ```json fence', () => {
    const text = '```json\n' + JSON.stringify({ questions: [question(), question(), question()] }) + '\n```';
    const out = parseQuiz(JSON.stringify({ type: 'result', is_error: false, result: text }), KEYS);
    expect(out).toHaveLength(3);
  });
  it('an envelope whose result is not a string is a QuizSchemaError', () => {
    expect(() => parseQuiz(JSON.stringify({ is_error: false, result: { questions: [] } }), KEYS)).toThrow(QuizSchemaError);
  });
});

describe('timeout and binary configuration', () => {
  it('SDD_LEARN_QUIZ_TIMEOUT_S sets the timeout in milliseconds', () => {
    expect(claudeOpts({ SDD_LEARN_QUIZ_TIMEOUT_S: '0.2' }).timeoutMs).toBe(200);
  });
  it('the timeout defaults to 90 seconds when the variable is unset', () => {
    expect(claudeOpts({}).timeoutMs).toBe(90_000);
  });
  it('SDD_LEARN_CLAUDE overrides the binary', () => {
    expect(claudeOpts({ SDD_LEARN_CLAUDE: '/opt/fake/claude' }).bin).toBe('/opt/fake/claude');
  });
  it('a missing binary raises ClaudeMissingError naming the configured binary through generateQuiz', async () => {
    const missing = '/nonexistent/claude-audit-xyz';
    const err = await generateQuiz({ id: 'a', title: 'A', body: 'B', sources: [{ title: 'S', url: 'https://e.org' }] }, { box: 0, interest: 'deep', misses: [] }, { bin: missing, timeoutMs: 2000 }).catch((e) => e);
    expect(err).toBeInstanceOf(ClaudeMissingError);
    expect(err.message).toContain(missing);
  });
});

describe('error responses never carry placeholder questions', () => {
  it.each([
    ['missing binary', { SDD_LEARN_CLAUDE: '/nonexistent/claude-audit-xyz' }, 502, 'ClaudeMissingError'],
    ['timeout', { FAKE_CLAUDE_MODE: 'sleep', SDD_LEARN_QUIZ_TIMEOUT_S: '0.2' }, 504, 'ClaudeTimeoutError'],
    ['garbage stdout', { FAKE_CLAUDE_MODE: 'garbage' }, 502, 'QuizSchemaError'],
    ['wrong count', { FAKE_CLAUDE_MODE: 'wrong-count' }, 502, 'QuizSchemaError'],
    ['unknown source', { FAKE_CLAUDE_MODE: 'unknown-source' }, 502, 'UnknownSourceError'],
    ['non-zero exit', { FAKE_CLAUDE_MODE: 'exit' }, 502, 'ClaudeExitError'],
  ])('%s responds %i %s without a questions key', async (_label, env, status, name) => {
    const s = server();
    const res = await withEnv(env, () => s.post(`/api/quiz/${LESSON}`));
    const body = (await res.json()) as any;
    expect(res.status).toBe(status);
    expect(body.error.name).toBe(name);
    expect(body).not.toHaveProperty('questions');
  });
});

describe('learner state under concurrency and stale locks', () => {
  it('an answer completes when a stale lock file is left behind, and removes the lock', async () => {
    const s = server();
    const { body } = await startQuiz(s);
    const lock = join(s.home, 'learner.json.lock');
    writeFileSync(lock, '99999');
    const old = new Date(Date.now() - 60_000);
    utimesSync(lock, old, old);
    const { res } = await answer(s, body.quizId, 0, 1);
    expect(res.status).toBe(200);
    expect(existsSync(lock), 'stale lock still present after answer').toBe(false);
    expect(s.state().history).toHaveLength(1);
  });
  it('concurrent answers across two quizzes keep every history entry', async () => {
    const s = server();
    const a = (await startQuiz(s)).body.quizId as string;
    const b = (await startQuiz(s)).body.quizId as string;
    const calls = [0, 1, 2].flatMap((i) => [answer(s, a, i, 1), answer(s, b, i, 1)]);
    const results = await Promise.all(calls);
    expect(results.map((r) => r.res.status)).toEqual(Array(6).fill(200));
    expect(s.state().history).toHaveLength(6);
  });
});

describe('SPA bundle quiz wiring', () => {
  const dist = join(LEARN_APP, 'dist');
  const bundle = (): string => {
    const js = readdirSync(join(dist, 'assets')).find((f) => f.endsWith('.js'));
    if (!js) throw new Error('no JS bundle in dist/assets');
    return readFileSync(join(dist, 'assets', js), 'utf8');
  };

  it('bundle contains the Retry control with its id', () => {
    const b = bundle();
    expect(b).toContain('Retry');
    expect(b).toContain('id="retry"');
  });
  it('bundle starts POST /api/quiz/<id> after rendering the lesson quiz section', () => {
    const b = bundle();
    const section = b.indexOf('id="quiz"');
    const request = b.search(/\/api\/quiz\/\$\{[\w$]+\}`,\{method:"POST",headers:\{"Content-Type":"application\/json"\}\}/);
    expect(section, 'quiz section not rendered in bundle').toBeGreaterThan(-1);
    expect(request, 'POST /api/quiz request not found in bundle').toBeGreaterThan(-1);
    expect(request).toBeGreaterThan(section);
  });
  it('bundle answers with POST /api/answer carrying quizId, questionIndex and chosen', () => {
    const b = bundle();
    expect(b).toContain('"/api/answer"');
    expect(b).toMatch(/quizId:\w+,questionIndex:\w+,chosen:\w+/);
  });
});

describe('bundled server.js with the fake CLI', () => {
  it('POST /api/quiz through the bundled server runs the fake CLI and returns 3 questions', async () => {
    const project = tmp('learn-quiz-bundled-proj-');
    const home = tmp('learn-quiz-bundled-home-');
    copyLearn(project);
    writeFileSync(join(home, 'learner.json'), JSON.stringify({ schema: 1, interest: { backend: 'deep' }, mastery: {}, history: [] }));
    const logFile = join(tmp('learn-quiz-bundled-log-'), 'argv.log');
    const srv = await startLearnServer({ project, home, env: { FAKE_CLAUDE_LOG: logFile } });
    const res = await fetch(`${srv.base}/api/quiz/${LESSON}`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    const body = (await res.json()) as any;
    expect(res.status).toBe(200);
    expect(body.questions).toHaveLength(3);
    expect(existsSync(logFile), 'fake CLI was not invoked; the real claude may have been used instead').toBe(true);
    expect(JSON.parse(readFileSync(logFile, 'utf8').trim().split('\n')[0])).toContain('--output-format');
  });
});

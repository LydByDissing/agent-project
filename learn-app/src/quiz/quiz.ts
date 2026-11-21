// [origin ref=llm-dsl-gu1y.7 req=REQ-OPERATOR-EDU-008,REQ-OPERATOR-EDU-009 c4=learn_app/question_generator]
//   [intent]Builds the personalised quiz prompt, runs headless claude -p, and strictly validates the returned 3 questions or throws a named error.[/intent]
//   [inv]Never returns placeholder or cached questions; every failure is one of the named errors.[/inv]
// [/origin]
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import type { SourceRef } from '../library/frontmatter.js';

export interface QuizQuestion {
  q: string;
  options: Array<{ text: string; explanation: string }>;
  correct: number;
  source: string;
}

export interface LearnerSlice {
  box: number;
  interest: string;
  misses: string[];
}

export interface QuizLesson {
  id: string;
  title: string;
  body: string;
  sources: SourceRef[];
}

export interface ClaudeOpts {
  bin?: string;
  timeoutMs?: number;
  model?: string;
}

export class ClaudeMissingError extends Error {
  constructor(readonly bin: string) {
    super(`claude binary not found: "${bin}" is not on PATH (set SDD_LEARN_CLAUDE to its location)`);
    this.name = 'ClaudeMissingError';
  }
}
export class ClaudeTimeoutError extends Error {
  constructor(readonly ms: number) {
    super(`claude -p did not finish within ${Math.round(ms / 1000)}s (raise SDD_LEARN_QUIZ_TIMEOUT_S)`);
    this.name = 'ClaudeTimeoutError';
  }
}
export class ClaudeExitError extends Error {
  constructor(readonly code: number | null, readonly stderr: string) {
    super(`claude -p failed (exit ${code}): ${stderr.slice(-400).trim() || 'no stderr'}`);
    this.name = 'ClaudeExitError';
  }
}
export class QuizSchemaError extends Error {
  constructor(detail: string) {
    super(`quiz output rejected: ${detail}`);
    this.name = 'QuizSchemaError';
  }
}
export class UnknownSourceError extends Error {
  constructor(readonly key: string, readonly known: string[]) {
    super(`question cites unknown source "${key}"; lesson sources are ${known.join(', ')}`);
    this.name = 'UnknownSourceError';
  }
}

export const sourceKeys = (sources: SourceRef[]): string[] => sources.map((_, i) => `s${i + 1}`);

const srcLine = (s: SourceRef, i: number): string =>
  `- s${i + 1}: ${s.title}${s.url ? ` (${s.url})` : s.path ? ` (${s.path}${s.line ? `:${s.line}` : ''})` : ''}`;

export function buildPrompt(lesson: QuizLesson, learner: LearnerSlice): string {
  const keys = sourceKeys(lesson.sources).join(', ');
  const misses = learner.misses.length
    ? learner.misses.map((m) => `- ${m}`).join('\n')
    : '- none recorded';
  return [
    'You write a 3-question multiple-choice check for one lesson, personalised to the learner. Reply with JSON only, no prose, no tools.',
    '',
    `Learner: this lesson is in Leitner box ${learner.box} of 5 (0 = never answered). Interest level in this subject: ${learner.interest}.`,
    'Questions the learner previously missed on this lesson (revisit these ideas in at least one question when any are listed):',
    misses,
    '',
    'Output schema: {"questions":[{"q":string,"options":[{"text":string,"explanation":string}],"correct":integer,"source":string}]}',
    'Rules: exactly 3 questions; 3 to 5 options each; "correct" is the 0-based index of the single right option; every option has an explanation saying why it is right or wrong; "source" is exactly one of these keys: ' + keys + '.',
    'Test understanding, not recall of wording. Use only facts from the lesson.',
    '',
    `Lesson id: ${lesson.id}`,
    `Lesson title: ${lesson.title}`,
    'Sources:',
    lesson.sources.map(srcLine).join('\n'),
    '',
    'Lesson body:',
    '<lesson>',
    lesson.body,
    '</lesson>',
  ].join('\n');
}

export function claudeOpts(env: NodeJS.ProcessEnv = process.env): Required<Pick<ClaudeOpts, 'bin' | 'timeoutMs'>> & ClaudeOpts {
  const secs = Number(env.SDD_LEARN_QUIZ_TIMEOUT_S ?? 90);
  return {
    bin: env.SDD_LEARN_CLAUDE && env.SDD_LEARN_CLAUDE !== '' ? env.SDD_LEARN_CLAUDE : 'claude',
    timeoutMs: (Number.isFinite(secs) && secs > 0 ? secs : 90) * 1000,
    model: env.SDD_LEARN_MODEL && env.SDD_LEARN_MODEL !== '' ? env.SDD_LEARN_MODEL : undefined,
  };
}

/** Runs claude -p with the prompt on stdin and returns the CLI's stdout. */
export function runClaude(prompt: string, opts: ClaudeOpts = {}): Promise<string> {
  const o = { ...claudeOpts(), ...opts };
  const args = ['-p', '--output-format', 'json', '--no-session-persistence'];
  if (o.model) args.push('--model', o.model);
  return new Promise((resolve, reject) => {
    // cwd is a neutral dir so project CLAUDE.md files cannot steer the quiz
    const child = spawn(o.bin, args, { cwd: tmpdir(), stdio: ['pipe', 'pipe', 'pipe'] });
    let out = '';
    let err = '';
    let done = false;
    const end = (fn: () => void): void => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      fn();
    };
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      end(() => reject(new ClaudeTimeoutError(o.timeoutMs)));
    }, o.timeoutMs);
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (err += d));
    child.on('error', (e) => end(() => reject((e as NodeJS.ErrnoException).code === 'ENOENT' ? new ClaudeMissingError(o.bin) : e)));
    child.on('close', (code) => end(() => (code === 0 ? resolve(out) : reject(new ClaudeExitError(code, err)))));
    child.stdin.on('error', () => undefined);
    child.stdin.end(prompt);
  });
}

function modelText(stdout: string): string {
  let env: unknown;
  try {
    env = JSON.parse(stdout);
  } catch {
    throw new QuizSchemaError(`claude stdout is not a JSON envelope: ${stdout.slice(0, 120)}`);
  }
  if (env === null || typeof env !== 'object') throw new QuizSchemaError('claude envelope is not an object');
  const e = env as { is_error?: unknown; result?: unknown };
  if (e.is_error === true) throw new ClaudeExitError(0, typeof e.result === 'string' ? e.result : 'is_error set in envelope');
  if (typeof e.result !== 'string') throw new QuizSchemaError('claude envelope has no string "result"');
  return e.result;
}

function extractJson(text: string): unknown {
  const fence = /```(?:json)?\s*([\s\S]*?)```/i.exec(text);
  const cand = (fence ? fence[1] : text).trim();
  try {
    return JSON.parse(cand);
  } catch {
    const a = cand.indexOf('{');
    const b = cand.lastIndexOf('}');
    if (a >= 0 && b > a) {
      try {
        return JSON.parse(cand.slice(a, b + 1));
      } catch {
        // fall through
      }
    }
    throw new QuizSchemaError(`model text is not valid JSON: ${cand.slice(0, 120)}`);
  }
}

const isRec = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);
const nonEmpty = (v: unknown): v is string => typeof v === 'string' && v.trim() !== '';

export function parseQuiz(stdout: string, keys: string[]): QuizQuestion[] {
  const root = extractJson(modelText(stdout));
  if (!isRec(root) || !Array.isArray(root.questions)) throw new QuizSchemaError('top level must be {"questions":[...]}');
  if (root.questions.length !== 3) throw new QuizSchemaError(`expected exactly 3 questions, got ${root.questions.length}`);
  return root.questions.map((raw, i): QuizQuestion => {
    const at = `questions[${i}]`;
    if (!isRec(raw)) throw new QuizSchemaError(`${at} is not an object`);
    if (!nonEmpty(raw.q)) throw new QuizSchemaError(`${at}.q must be a non-empty string`);
    const opts = raw.options;
    if (!Array.isArray(opts) || opts.length < 3 || opts.length > 5) {
      throw new QuizSchemaError(`${at}.options must have 3-5 entries, got ${Array.isArray(opts) ? opts.length : typeof opts}`);
    }
    const options = opts.map((o, j) => {
      if (!isRec(o) || !nonEmpty(o.text) || !nonEmpty(o.explanation)) {
        throw new QuizSchemaError(`${at}.options[${j}] needs non-empty text and explanation`);
      }
      return { text: o.text, explanation: o.explanation };
    });
    const c = raw.correct;
    if (typeof c !== 'number' || !Number.isInteger(c) || c < 0 || c >= options.length) {
      throw new QuizSchemaError(`${at}.correct must be a single integer index in 0..${options.length - 1}, got ${JSON.stringify(c)}`);
    }
    if (!nonEmpty(raw.source)) throw new QuizSchemaError(`${at}.source must be a source key`);
    if (!keys.includes(raw.source)) throw new UnknownSourceError(raw.source, keys);
    return { q: raw.q, options, correct: c, source: raw.source };
  });
}

export async function generateQuiz(lesson: QuizLesson, learner: LearnerSlice, opts: ClaudeOpts = {}): Promise<QuizQuestion[]> {
  const stdout = await runClaude(buildPrompt(lesson, learner), opts);
  return parseQuiz(stdout, sourceKeys(lesson.sources));
}

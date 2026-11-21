// [origin ref=llm-dsl-gu1y.9,llm-dsl-gu1y.5,llm-dsl-gu1y.7 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-006,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-008,REQ-OPERATOR-EDU-009,REQ-OPERATOR-EDU-010 c4=learn_app/learn_server]
//   [intent]Builds the Hono app: JSON API (now, learner, interest, tree, next, lesson, asset, quiz, answer) plus static serving of the built SPA.[/intent]
//   [inv]Every project path served (lessons, SVG assets, now.json) resolves under the project root via resolveUnder; PUT /api/interest writes nothing unless every key and value validates.[/inv]
// [/origin]
import { existsSync, readFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { Hono } from 'hono';
import { type Library, type Lesson, LibraryError, loadLibrary } from '../library/load.js';
import { MASTERED_BOX, type Now, interestFor, prerequisitesMet, select, visibleAtInterest } from '../selector/select.js';
import { randomUUID } from 'node:crypto';
import { type ClaudeOpts, type QuizQuestion, ClaudeExitError, ClaudeMissingError, ClaudeTimeoutError, QuizSchemaError, UnknownSourceError, claudeOpts, generateQuiz, sourceKeys } from '../quiz/quiz.js';
import { leitner } from '../state/leitner.js';
import { type Interest, learnHome, readLearner, updateLearner } from '../state/learner.js';
import { PathEscapeError, resolveUnder } from './paths.js';

export interface AppOptions {
  project: string;
  distDir: string;
  /** Directory holding learner.json; defaults to $SDD_LEARN_HOME or ~/.sdd. */
  home?: string;
  /** Today as YYYY-MM-DD; defaults to the local date. Called once per answer in the handler. */
  today?: () => string;
  /** Claude CLI options, resolved per request; defaults to SDD_LEARN_* env. */
  claude?: () => ClaudeOpts;
  /** Epoch milliseconds; defaults to Date.now. Drives quiz expiry. */
  now?: () => number;
}

interface QuizState {
  lessonId: string;
  questions: QuizQuestion[];
  keys: string[];
  sources: Array<{ title: string; url?: string; path?: string; line?: number }>;
  chosen: Array<number | undefined>;
  createdAt: number;
}

const MISS_LIMIT = 5;
const QUIZ_TTL_MS = 60 * 60 * 1000;
const INTEREST_VALUES: readonly Interest[] = ['deep', 'basics', 'skip'];
const short = (q: string): string => (q.length > 90 ? `${q.slice(0, 89)}…` : q);

const NOW_FILE = '.sdd/now.json';
const ID_PATH = /^[a-z0-9][a-z0-9._-]*(\/[a-z0-9][a-z0-9._-]*)*$/i;

function today(): string {
  const d = new Date();
  const p = (n: number): string => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function readNow(project: string): Now {
  const file = resolveUnder(project, NOW_FILE);
  if (!existsSync(file)) return { jobs: [] };
  const raw = JSON.parse(readFileSync(file, 'utf8')) as Record<string, unknown>;
  const jobs = Array.isArray(raw.jobs) ? raw.jobs : [];
  return { ...raw, jobs: jobs.map((j) => ({ ...j, topics: Array.isArray(j.topics) ? j.topics : [], status: String(j.status ?? 'running') })) } as Now;
}

const summary = (l: Lesson) => ({ id: l.id, title: l.title, level: l.level, domain: l.domain, topic: l.topic, order: l.order });

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
  '.ico': 'image/x-icon',
};

function interestKeys(lib: Library): Set<string> {
  return new Set(lib.domains.flatMap((d) => [d.id, ...d.topics.map((t) => t.id)]));
}

export function createApp({ project, distDir, home, today: todayFn = today, claude = claudeOpts, now = Date.now }: AppOptions): Hono {
  const app = new Hono();
  const quizzes = new Map<string, QuizState>();
  const homeDir = (): string => home ?? learnHome();
  const library = (): Library => loadLibrary(project);
  const evictQuizzes = (at: number): void => {
    for (const [id, q] of quizzes) if (at - q.createdAt > QUIZ_TTL_MS) quizzes.delete(id);
  };

  app.onError((err, c) => {
    if (err instanceof ClaudeMissingError || err instanceof ClaudeExitError || err instanceof QuizSchemaError || err instanceof UnknownSourceError) {
      return c.json({ error: { name: err.name, message: err.message } }, 502);
    }
    if (err instanceof ClaudeTimeoutError) return c.json({ error: { name: err.name, message: err.message } }, 504);
    if (err instanceof LibraryError) return c.json({ error: 'library_invalid', issues: err.issues }, 500);
    if (err instanceof PathEscapeError) return c.json({ error: 'not_found' }, 404);
    if (err instanceof SyntaxError) return c.json({ error: 'now_invalid', message: err.message }, 500);
    return c.json({ error: 'internal', message: err.message }, 500);
  });

  app.get('/api/health', (c) => c.json({ ok: true }));

  app.get('/api/now', (c) => c.json(readNow(project)));

  app.get('/api/learner', (c) => c.json(readLearner(homeDir())));

  app.get('/api/interest', (c) => {
    const lib = library();
    return c.json({
      interest: readLearner(homeDir()).interest,
      domains: lib.domains.map((d) => ({ id: d.id, title: d.title, topics: d.topics.map((t) => ({ id: t.id, title: t.title })) })),
    });
  });

  app.put('/api/interest', async (c) => {
    const body = (await c.req.json().catch(() => undefined)) as unknown;
    if (body === null || typeof body !== 'object' || Array.isArray(body)) {
      return c.json({ error: 'bad_body', message: 'body must be {key, value} or a map of key to value' }, 400);
    }
    const rec = body as Record<string, unknown>;
    const pairs: Array<[string, unknown]> = typeof rec.key === 'string' && 'value' in rec ? [[rec.key, rec.value]] : Object.entries(rec);
    const known = interestKeys(library());
    for (const [key, value] of pairs) {
      if (!known.has(key)) return c.json({ error: 'unknown_key', key, message: `unknown interest key ${JSON.stringify(key)}: use a domain or domain/topic in learn/` }, 400);
      if (!INTEREST_VALUES.includes(value as Interest)) {
        return c.json({ error: 'bad_value', key, value, message: `value ${JSON.stringify(value)} for ${JSON.stringify(key)} must be deep, basics or skip` }, 400);
      }
    }
    const next = await updateLearner(homeDir(), (cur) => {
      for (const [key, value] of pairs) cur.interest[key] = value as Interest;
    });
    return c.json({ interest: next.interest });
  });

  app.get('/api/tree', (c) => {
    const learner = readLearner(homeDir());
    const lib = library();
    return c.json({
      domains: lib.domains.map((d) => ({
        id: d.id,
        title: d.title,
        interest: interestFor(learner, d.id),
        topics: d.topics.map((t) => {
          const interest = interestFor(learner, d.id, t.slug);
          return {
            id: t.id,
            title: t.title,
            interest,
            lessons: t.lessons.map((l) => {
              const mastery = learner.mastery[l.id] ?? null;
              let status: string;
              if (interest === 'skip') status = 'skipped';
              else if (!visibleAtInterest(l, interest)) status = 'not_at_basics';
              else if (!mastery && !prerequisitesMet(l, learner)) status = 'locked';
              else status = mastery ? 'learning' : 'new';
              return { ...summary(l), mastery, status };
            }),
          };
        }),
      })),
      mastered_box: MASTERED_BOX,
    });
  });

  app.get('/api/next', (c) => {
    const sel = select(library(), readLearner(homeDir()), readNow(project), today());
    return c.json({ lesson: sel.lesson ? summary(sel.lesson) : null, reason: sel.reason, what_changed: sel.what_changed });
  });

  app.get('/api/lesson/*', (c) => {
    let id: string;
    try {
      id = decodeURIComponent(new URL(c.req.url).pathname.slice('/api/lesson/'.length));
    } catch {
      return c.json({ error: 'not_found' }, 404);
    }
    if (!ID_PATH.test(id)) return c.json({ error: 'not_found' }, 404);
    if (!existsSync(join(project, 'learn'))) return c.json({ error: 'not_found' }, 404);
    const lib = library();
    const lesson = lib.lessons.find((l) => l.id === id);
    if (!lesson) return c.json({ error: 'not_found' }, 404);
    const learner = readLearner(homeDir());
    const topic = lib.domains.find((d) => d.id === lesson.domain)?.topics.find((t) => t.slug === lesson.topic);
    const byId = new Map(lib.lessons.map((l) => [l.id, l]));
    return c.json({
      ...summary(lesson),
      topic_title: topic?.title ?? lesson.topic,
      topic_position: (topic?.lessons.findIndex((l) => l.id === id) ?? 0) + 1,
      topic_size: topic?.lessons.length ?? 1,
      requires: lesson.requires.map((r) => ({ id: r, title: byId.get(r)?.title ?? r, mastered: (learner.mastery[r]?.box ?? 0) >= MASTERED_BOX })),
      sources: lesson.sources,
      updated: lesson.updated,
      stale: lesson.stale,
      body: lesson.body,
      diagrams: lesson.diagrams,
    });
  });

  app.post('/api/quiz/*', async (c) => {
    let id: string;
    try {
      id = decodeURIComponent(new URL(c.req.url).pathname.slice('/api/quiz/'.length));
    } catch {
      return c.json({ error: 'not_found' }, 404);
    }
    evictQuizzes(now());
    if (!ID_PATH.test(id) || !existsSync(join(project, 'learn'))) return c.json({ error: 'not_found' }, 404);
    const lesson = library().lessons.find((l) => l.id === id);
    if (!lesson) return c.json({ error: 'not_found' }, 404);
    const learner = readLearner(homeDir());
    const misses = [...new Set(learner.history.filter((h) => h.lesson === id && h.chosen !== h.correct).map((h) => h.q))].slice(-MISS_LIMIT);
    const slice = { box: learner.mastery[id]?.box ?? 0, interest: interestFor(learner, lesson.domain, lesson.topic), misses };
    const started = now();
    const questions = await generateQuiz(lesson, slice, claude());
    const quizId = randomUUID();
    const keys = sourceKeys(lesson.sources);
    quizzes.set(quizId, { lessonId: id, questions, keys, sources: lesson.sources, chosen: questions.map(() => undefined), createdAt: now() });
    return c.json({
      quizId,
      seconds: Math.round((now() - started) / 100) / 10,
      persona: { box: slice.box, interest: slice.interest, misses },
      questions: questions.map((q) => ({ q: q.q, options: q.options.map((o) => o.text) })),
    });
  });

  app.post('/api/answer', async (c) => {
    const body = (await c.req.json().catch(() => null)) as { quizId?: unknown; questionIndex?: unknown; chosen?: unknown } | null;
    const quiz = typeof body?.quizId === 'string' ? quizzes.get(body.quizId) : undefined;
    if (!body || !quiz) return c.json({ error: 'unknown_quiz' }, 404);
    const qi = body.questionIndex;
    const q = typeof qi === 'number' && Number.isInteger(qi) ? quiz.questions[qi] : undefined;
    if (!q || typeof qi !== 'number') return c.json({ error: 'bad_question_index' }, 400);
    const chosen = body.chosen;
    if (typeof chosen !== 'number' || !Number.isInteger(chosen) || chosen < 0 || chosen >= q.options.length) return c.json({ error: 'bad_choice' }, 400);
    if (quiz.chosen[qi] !== undefined) return c.json({ error: 'already_answered' }, 409);
    quiz.chosen[qi] = chosen;
    const day = todayFn();
    const now = new Date().toISOString();
    const done = quiz.chosen.every((x) => x !== undefined);
    const allCorrect = done && quiz.chosen.every((x, i) => x === quiz.questions[i].correct);
    const srcIdx = quiz.keys.indexOf(q.source);
    let result: { box: number; due: string } | undefined;
    try {
      await updateLearner(homeDir(), (cur) => {
      cur.history.push({ lesson: quiz.lessonId, q: short(q.q), chosen, correct: q.correct, at: now, explanation: q.options[chosen].explanation, source: q.source });
      if (done) {
        result = leitner(cur.mastery[quiz.lessonId]?.box ?? 0, allCorrect, day);
        cur.mastery[quiz.lessonId] = result;
      }
      });
    } catch (err) {
      quiz.chosen[qi] = undefined;
      throw err;
    }
    if (done) quizzes.delete(body.quizId as string);
    return c.json({
      correct: chosen === q.correct,
      correctIndex: q.correct,
      explanations: q.options.map((o) => o.explanation),
      source: { key: q.source, ...quiz.sources[srcIdx] },
      ...(result ? { complete: true, allCorrect, box: result.box, due: result.due } : { complete: false }),
    });
  });

  app.get('/api/asset/*', async (c) => {
    let rel: string;
    try {
      rel = decodeURIComponent(new URL(c.req.url).pathname.slice('/api/asset/'.length));
    } catch {
      return c.json({ error: 'not_found' }, 404);
    }
    if (!rel.endsWith('.svg')) return c.json({ error: 'not_found' }, 404);
    try {
      const file = resolveUnder(join(project, 'learn'), rel);
      const body = await readFile(file);
      return c.body(body, 200, {
        'Content-Type': 'image/svg+xml',
        'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'",
        'X-Content-Type-Options': 'nosniff',
      });
    } catch (err) {
      if (err instanceof PathEscapeError || (err as NodeJS.ErrnoException).code) return c.json({ error: 'not_found' }, 404);
      throw err;
    }
  });

  app.all('/api/*', (c) => c.json({ error: 'not_found' }, 404));

  app.get('*', async (c) => {
    let pathname: string;
    try {
      pathname = decodeURIComponent(new URL(c.req.url).pathname);
    } catch {
      return c.text('Not found', 404);
    }
    try {
      const file = resolveUnder(distDir, pathname === '/' ? 'index.html' : pathname);
      const body = await readFile(file);
      return c.body(body, 200, { 'Content-Type': MIME[extname(file)] ?? 'application/octet-stream' });
    } catch (err) {
      if (err instanceof PathEscapeError || (err as NodeJS.ErrnoException).code) return c.text('Not found', 404);
      throw err;
    }
  });

  return app;
}

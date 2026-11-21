// [origin ref=llm-dsl-gu1y.5 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_server]
//   [intent]Builds the Hono app: JSON API (now, learner, tree, next, lesson, asset) plus static serving of the built SPA.[/intent]
//   [inv]Every project path served (lessons, SVG assets, now.json) resolves under the project root via resolveUnder.[/inv]
// [/origin]
import { existsSync, readFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { Hono } from 'hono';
import { type Library, type Lesson, LibraryError, loadLibrary } from '../library/load.js';
import { MASTERED_BOX, type Now, interestFor, prerequisitesMet, select, visibleAtInterest } from '../selector/select.js';
import { learnHome, readLearner } from '../state/learner.js';
import { PathEscapeError, resolveUnder } from './paths.js';

export interface AppOptions {
  project: string;
  distDir: string;
  /** Directory holding learner.json; defaults to $SDD_LEARN_HOME or ~/.sdd. */
  home?: string;
}

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

export function createApp({ project, distDir, home }: AppOptions): Hono {
  const app = new Hono();
  const homeDir = (): string => home ?? learnHome();
  const library = (): Library => loadLibrary(project);

  app.onError((err, c) => {
    if (err instanceof LibraryError) return c.json({ error: 'library_invalid', issues: err.issues }, 500);
    if (err instanceof PathEscapeError) return c.json({ error: 'not_found' }, 404);
    if (err instanceof SyntaxError) return c.json({ error: 'now_invalid', message: err.message }, 500);
    return c.json({ error: 'internal', message: err.message }, 500);
  });

  app.get('/api/health', (c) => c.json({ ok: true }));

  app.get('/api/now', (c) => c.json(readNow(project)));

  app.get('/api/learner', (c) => c.json(readLearner(homeDir())));

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

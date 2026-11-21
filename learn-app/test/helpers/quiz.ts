// [origin ref=llm-dsl-gu1y.17 req=REQ-OPERATOR-EDU-008,REQ-OPERATOR-EDU-009 c4=learn_app/question_generator]
//   [intent]Shared in-process quiz test fixtures: an app over a seed-learn copy with a private learner home and injected clocks, plus a stub claude binary that prints fixed stdout.[/intent]
// [/origin]
import { chmodSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { AppOptions } from '../../src/server/app.js';
import { makeApp } from './app.js';
import { copyLearn } from './server.js';
import { tmp } from './tmp.js';

export const LESSON = 'backend/http-caching/01-freshness';
export const OTHER = 'backend/http-caching/02-revalidation';

/** A learner app over a preserved-timestamp copy of learn/, learner.json seeded (backend: deep by default). */
export function quizServer(learner: Record<string, unknown> = {}, opts: { today?: string; now?: () => number; claude?: AppOptions['claude'] } = {}) {
  const project = tmp('learn-quiz-proj-');
  const home = tmp('learn-quiz-home-');
  copyLearn(project);
  writeFileSync(join(home, 'learner.json'), JSON.stringify({ schema: 1, interest: { backend: 'deep' }, mastery: {}, history: [], ...learner }));
  const app = makeApp({ project, distDir: project, home, today: () => opts.today ?? '2026-11-21', ...(opts.now ? { now: opts.now } : {}), ...(opts.claude ? { claude: opts.claude } : {}) });
  const post = (p: string, body?: unknown) =>
    app.request(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const state = () => JSON.parse(readFileSync(join(home, 'learner.json'), 'utf8'));
  return { app, post, state, home, project };
}
export type QuizServer = ReturnType<typeof quizServer>;

/** Writes an executable stub that ignores stdin and prints `stdout`, to drive error envelopes through the server. */
export function stubBinary(stdout: string): string {
  const bin = join(tmp('learn-stub-'), 'claude-stub.mjs');
  writeFileSync(bin, `#!${process.execPath}\nprocess.stdin.resume();\nprocess.stdin.on('end', () => process.stdout.write(${JSON.stringify(stdout)}));\n`);
  chmodSync(bin, 0o755);
  return bin;
}

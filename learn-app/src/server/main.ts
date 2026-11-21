// [origin ref=llm-dsl-gu1y.5 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_server]
//   [intent]CLI entry point: parses --project, creates learner.json (refusing unknown schemas) and starts the server bound to 127.0.0.1 only.[/intent]
//   [inv]The listener hostname is always 127.0.0.1.[/inv]
// [/origin]
import { existsSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { serve } from '@hono/node-server';
import { learnHome, initLearner } from '../state/learner.js';
import { createApp } from './app.js';

export const HOST = '127.0.0.1';

function parseProject(argv: string[]): string {
  const i = argv.indexOf('--project');
  const value = i >= 0 ? argv[i + 1] : undefined;
  if (!value) throw new Error('usage: node server.js --project <dir>');
  const dir = resolve(value);
  if (!existsSync(dir) || !statSync(dir).isDirectory()) throw new Error(`project directory not found: ${dir}`);
  return dir;
}

const here = dirname(fileURLToPath(import.meta.url));
const distDir = [join(here, 'dist'), join(here, '..', '..', 'dist')].find(existsSync) ?? join(here, 'dist');

try {
  const project = parseProject(process.argv.slice(2));
  const port = Number(process.env.SDD_LEARN_PORT ?? 4747);
  const home = learnHome();
  await initLearner(home);
  serve({ fetch: createApp({ project, distDir, home }).fetch, hostname: HOST, port }, (info) => {
    console.log(`SDD Learn listening on http://${HOST}:${info.port} (project ${project}, learner ${home})`);
  });
} catch (err) {
  console.error((err as Error).message);
  process.exit(1);
}

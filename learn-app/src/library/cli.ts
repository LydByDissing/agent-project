// [origin ref=llm-dsl-gu1y.3 req=REQ-OPERATOR-EDU-001,REQ-OPERATOR-EDU-002,REQ-OPERATOR-EDU-003 c4=learn_app/lesson_library]
//   [intent]Implements the `learn validate --project <dir>` command: returns the exit code and the lines to print, without touching the process.[/intent]
//   [inv]A failed validation returns a non-zero code and lists every problem on stderr lines, never a summary.[/inv]
// [/origin]
import { LibraryError, loadLibrary } from './load.js';

export interface CliResult {
  code: number;
  stdout: string[];
  stderr: string[];
}

const USAGE = 'usage: node learn-app/cli.js validate --project <dir>';

export function runCli(argv: string[]): CliResult {
  const [cmd, ...rest] = argv;
  if (cmd !== 'validate') return { code: 2, stdout: [], stderr: [USAGE] };
  const i = rest.indexOf('--project');
  const project = i >= 0 ? rest[i + 1] : undefined;
  if (!project) return { code: 2, stdout: [], stderr: [USAGE] };

  try {
    const lib = loadLibrary(project);
    const topics = lib.domains.reduce((n, d) => n + d.topics.length, 0);
    return {
      code: 0,
      stdout: [
        `learn OK: ${lib.domains.length} domains, ${topics} topics, ${lib.lessons.length} lessons, ${lib.edges.length} prerequisite edges`,
      ],
      stderr: [],
    };
  } catch (err) {
    if (!(err instanceof LibraryError)) throw err;
    return {
      code: 1,
      stdout: [],
      stderr: [`learn validate: ${err.issues.length} problem(s)`, ...err.issues.map((s) => `  - ${s}`)],
    };
  }
}

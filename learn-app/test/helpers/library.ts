// [origin ref=llm-dsl-gu1y.17 req=REQ-OPERATOR-EDU-001,REQ-OPERATOR-EDU-002,REQ-OPERATOR-EDU-003 c4=learn_app/lesson_library]
//   [intent]Shared fixture builders for lesson library tests: temp projects from a file map, index.yaml and lesson Markdown text, and the two-lesson IAC tree.[/intent]
// [/origin]
import { mkdirSync, utimesSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { tmp } from './tmp.js';

export function makeLibProject(files: Record<string, string>): string {
  const root = tmp('learn-lib-');
  for (const [rel, text] of Object.entries(files)) {
    const abs = join(root, rel);
    mkdirSync(dirname(abs), { recursive: true });
    writeFileSync(abs, text);
  }
  return root;
}

export function setMtime(root: string, rel: string, when: Date): void {
  utimesSync(join(root, rel), when, when);
}

export const INDEX = (title: string) => `title: ${title}\nsummary: Summary of ${title}.\n`;

export function lessonMd(id: string, opts: { level?: string; requires?: string[]; sources?: string; body?: string; updated?: string } = {}): string {
  const requires = opts.requires ?? [];
  const reqText = requires.length === 0 ? '[]' : '\n' + requires.map((r) => `  - ${r}`).join('\n');
  const sources = opts.sources ?? '  - title: Spec\n    url: https://www.rfc-editor.org/rfc/rfc9110#name-etag';
  return [
    '---',
    `id: ${id}`,
    `title: Lesson ${id}`,
    `level: ${opts.level ?? 'intro'}`,
    `requires: ${reqText}`,
    'sources:',
    sources,
    `updated: ${opts.updated ?? '2026-11-21'}`,
    '---',
    opts.body ?? 'Body text for the lesson.',
    '',
  ].join('\n');
}

export const IAC = {
  'learn/iac/index.yaml': INDEX('Infrastructure as code'),
  'learn/iac/terraform-state/index.yaml': INDEX('Terraform state'),
  'learn/iac/terraform-state/01-what-state-is.md': lessonMd('iac/terraform-state/01-what-state-is', { level: 'intro' }),
  'learn/iac/terraform-state/02-remote-backends.md': lessonMd('iac/terraform-state/02-remote-backends', {
    level: 'working',
    requires: ['iac/terraform-state/01-what-state-is'],
  }),
};

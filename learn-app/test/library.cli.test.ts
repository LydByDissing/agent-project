// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.4 req=REQ-OPERATOR-EDU-001,REQ-OPERATOR-EDU-002,REQ-OPERATOR-EDU-003 c4=learn_app/lesson_library]
//   [intent]Runs the bundled learn-app/cli.js as a child process to verify `learn validate` exit codes and named problems, and checks that no docs/source file includes or links into learn/.[/intent]
// [/origin]
import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { IAC, INDEX, lessonMd, makeLibProject, setMtime } from './helpers/library.js';

const LEARN_APP = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = resolve(LEARN_APP, '..');
const CLI = join(LEARN_APP, 'cli.js');
const DOCS_SOURCE = join(REPO, 'docs', 'source');

const makeProject = makeLibProject;
const lesson = lessonMd;

interface Run {
  code: number | null;
  stdout: string[];
  stderr: string[];
}

function lines(text: string): string[] {
  return text.split('\n').filter((l) => l.length > 0);
}

/** Runs the bundled CLI exactly as an operator would: `node learn-app/cli.js validate --project <dir>`. */
function validate(root: string): Run {
  const r = spawnSync(process.execPath, [CLI, 'validate', '--project', root], { encoding: 'utf8' });
  return { code: r.status, stdout: lines(r.stdout), stderr: lines(r.stderr) };
}

/** The per-problem lines printed by the CLI (indented with "  - "), without the prefix. */
function problemLines(run: Run): string[] {
  return run.stderr.filter((l) => l.startsWith('  - ')).map((l) => l.slice(4));
}

/** The file named at the start of a problem line: everything before the first ": ". */
function namedFile(problem: string): string {
  return problem.slice(0, problem.indexOf(': '));
}

describe('learn validate (bundled cli.js): exit codes and named problems', () => {
  it('exits 0 and prints the tree summary for a valid fixture tree', () => {
    const run = validate(makeProject(IAC));
    expect(run.code).toBe(0);
    expect(run.stdout).toEqual(['learn OK: 1 domains, 1 topics, 2 lessons, 1 prerequisite edges']);
    expect(run.stderr).toEqual([]);
  });

  it('exits 1 and names the lesson file when a source has neither url nor path', () => {
    const run = validate(
      makeProject({
        ...IAC,
        'learn/iac/terraform-state/02-remote-backends.md': lesson('iac/terraform-state/02-remote-backends', {
          level: 'working',
          requires: ['iac/terraform-state/01-what-state-is'],
          sources: '  - title: Floating claim',
        }),
      }),
    );
    expect(run.code).toBe(1);
    expect(run.stdout).toEqual([]);
    expect(problemLines(run)).toEqual([
      'learn/iac/terraform-state/02-remote-backends.md: sources[1] (Floating claim) has neither url nor path',
    ]);
  });

  it('exits 1 and names the lesson file when a lesson has empty sources', () => {
    const run = validate(
      makeProject({
        ...IAC,
        'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', { sources: '  []' }),
      }),
    );
    expect(run.code).toBe(1);
    expect(problemLines(run)).toEqual(['learn/iac/terraform-state/01-what-state-is.md: sources is empty (at least one source is required)']);
  });

  it('exits 1 and names the lesson file when requires names a missing lesson id', () => {
    const run = validate(
      makeProject({
        ...IAC,
        'learn/iac/terraform-state/02-remote-backends.md': lesson('iac/terraform-state/02-remote-backends', {
          level: 'working',
          requires: ['iac/terraform-state/09-missing'],
        }),
      }),
    );
    expect(run.code).toBe(1);
    expect(problemLines(run)).toEqual([
      'learn/iac/terraform-state/02-remote-backends.md: requires "iac/terraform-state/09-missing", which is not a lesson under learn/',
    ]);
  });

  it('exits 1 and reports the full three-lesson cycle when prerequisites loop back', () => {
    const run = validate(
      makeProject({
        'learn/iac/index.yaml': INDEX('IaC'),
        'learn/iac/terraform-state/index.yaml': INDEX('State'),
        'learn/iac/terraform-state/01-a.md': lesson('iac/terraform-state/01-a', { requires: ['iac/terraform-state/03-c'] }),
        'learn/iac/terraform-state/02-b.md': lesson('iac/terraform-state/02-b', {
          level: 'working',
          requires: ['iac/terraform-state/01-a'],
        }),
        'learn/iac/terraform-state/03-c.md': lesson('iac/terraform-state/03-c', {
          level: 'deep',
          requires: ['iac/terraform-state/02-b'],
        }),
      }),
    );
    expect(run.code).toBe(1);
    const problems = problemLines(run);
    expect(problems).toHaveLength(1);
    expect(namedFile(problems[0])).toBe('learn/iac/terraform-state/01-a.md');
    expect(problems[0]).toContain(
      'prerequisite cycle iac/terraform-state/01-a -> iac/terraform-state/03-c -> iac/terraform-state/02-b -> iac/terraform-state/01-a',
    );
  });

  it('exits 1 and names the lesson file when a referenced SVG is missing', () => {
    const body = 'See the flow: ![flow](diagrams/state-flow.svg)';
    const run = validate(
      makeProject({
        ...IAC,
        'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', { body }),
        'learn/iac/terraform-state/diagrams/state-flow.puml': '@startuml\n@enduml\n',
      }),
    );
    expect(run.code).toBe(1);
    const problems = problemLines(run);
    expect(problems).toHaveLength(1);
    expect(namedFile(problems[0])).toBe('learn/iac/terraform-state/01-what-state-is.md');
    expect(problems[0]).toContain('diagrams/state-flow.svg, which is missing');
  });

  it('exits 1 and names the lesson file when a referenced SVG is older than its .puml source', () => {
    const body = 'See the flow: ![flow](diagrams/state-flow.svg)';
    const root = makeProject({
      ...IAC,
      'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', { body }),
      'learn/iac/terraform-state/diagrams/state-flow.puml': '@startuml\n@enduml\n',
      'learn/iac/terraform-state/diagrams/state-flow.svg': '<svg/>',
    });
    setMtime(root, 'learn/iac/terraform-state/diagrams/state-flow.svg', new Date('2026-01-01T00:00:00Z'));
    setMtime(root, 'learn/iac/terraform-state/diagrams/state-flow.puml', new Date('2026-06-01T00:00:00Z'));
    const run = validate(root);
    expect(run.code).toBe(1);
    const problems = problemLines(run);
    expect(problems).toHaveLength(1);
    expect(namedFile(problems[0])).toBe('learn/iac/terraform-state/01-what-state-is.md');
    expect(problems[0]).toContain('diagrams/state-flow.svg is older than its source diagrams/state-flow.puml');
  });

  it('exits 0 when a referenced SVG is newer than its .puml source (positive control)', () => {
    const body = 'See the flow: ![flow](diagrams/state-flow.svg)';
    const root = makeProject({
      ...IAC,
      'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', { body }),
      'learn/iac/terraform-state/diagrams/state-flow.puml': '@startuml\n@enduml\n',
      'learn/iac/terraform-state/diagrams/state-flow.svg': '<svg/>',
    });
    setMtime(root, 'learn/iac/terraform-state/diagrams/state-flow.puml', new Date('2026-01-01T00:00:00Z'));
    setMtime(root, 'learn/iac/terraform-state/diagrams/state-flow.svg', new Date('2026-06-01T00:00:00Z'));
    const run = validate(root);
    expect(run.code).toBe(0);
    expect(run.stdout).toEqual(['learn OK: 1 domains, 1 topics, 2 lessons, 1 prerequisite edges']);
  });

  it('exits 1 with a header count matching the lines, and every problem line names an existing file', () => {
    const root = makeProject({
      ...IAC,
      'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', { sources: '  []' }),
      'learn/iac/terraform-state/02-remote-backends.md': lesson('iac/terraform-state/02-remote-backends', {
        level: 'working',
        requires: ['iac/terraform-state/09-missing'],
      }),
    });
    const run = validate(root);
    expect(run.code).toBe(1);
    expect(run.stderr[0]).toBe('learn validate: 2 problem(s)');
    const problems = problemLines(run);
    expect(problems).toHaveLength(2);
    expect(run.stderr.slice(1)).toHaveLength(problems.length);
    for (const p of problems) {
      const file = namedFile(p);
      expect(file, `problem line does not name a lesson file: ${p}`).toMatch(/^learn\/.+\.md$/);
      expect(existsSync(join(root, file)), `named file ${file} does not exist under the project`).toBe(true);
    }
  });

  it('exits 2 with usage on stderr when no project directory is given', () => {
    const r = spawnSync(process.execPath, [CLI, 'validate'], { encoding: 'utf8' });
    expect(r.status).toBe(2);
    expect(r.stderr).toContain('usage: node learn-app/cli.js validate --project <dir>');
  });

  it('exits 2 for an unknown subcommand', () => {
    expect(spawnSync(process.execPath, [CLI, 'render'], { encoding: 'utf8' }).status).toBe(2);
  });
});

describe('learn validate (bundled cli.js): the repo seed', () => {
  it('exits 0 for the repo learn/ with the expected tree summary', () => {
    const run = validate(REPO);
    expect(run.code).toBe(0);
    expect(run.stdout).toEqual(['learn OK: 1 domains, 1 topics, 2 lessons, 1 prerequisite edges']);
    expect(run.stderr).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// docs/source must not include, link or toctree into learn/ (prose is fine).
// ---------------------------------------------------------------------------

const DOC_EXTENSIONS = ['.rst', '.md', '.txt', '.py', '.toml', '.yaml', '.yml', '.cfg'];
const LEARN_PATH = /(^|[\s`'"(<\/])learn\//;

/** Returns the lines of `text` that include, link, or toctree-list a path under learn/. */
function findLearnLinks(text: string): string[] {
  const hits: string[] = [];
  let toctreeIndent: number | undefined;
  text.split(/\r?\n/).forEach((line, i) => {
    const n = i + 1;
    const indent = line.length - line.trimStart().length;
    const trimmed = line.trim();

    if (toctreeIndent !== undefined) {
      if (trimmed === '') return;
      if (indent > toctreeIndent) {
        if (!trimmed.startsWith(':') && LEARN_PATH.test(trimmed)) hits.push(`${n}: ${trimmed}`);
        return;
      }
      toctreeIndent = undefined;
    }

    const directive = /^\s*\.\.\s+(include|literalinclude|image|figure|download|csv-table)::\s*(.*)$/.exec(line);
    if (directive && LEARN_PATH.test(directive[2])) {
      hits.push(`${n}: ${trimmed}`);
      return;
    }
    if (/^\s*\.\.\s+toctree::/.test(line)) {
      toctreeIndent = indent;
      return;
    }
    const role = /:(doc|download|include):`([^`]*)`/g;
    for (const m of line.matchAll(role)) {
      if (LEARN_PATH.test(m[2])) hits.push(`${n}: ${trimmed}`);
    }
    const hyperlink = /`[^`]*<([^>]+)>`__?/g;
    for (const m of line.matchAll(hyperlink)) {
      if (!m[1].includes('://') && LEARN_PATH.test(m[1])) hits.push(`${n}: ${trimmed}`);
    }
    const target = /^\s*\.\.\s+_[^:]+:\s*(\S+)\s*$/.exec(line);
    if (target && !target[1].includes('://') && LEARN_PATH.test(target[1])) hits.push(`${n}: ${trimmed}`);
  });
  return hits;
}

function docFiles(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const abs = join(dir, e.name);
    if (e.isDirectory()) out.push(...docFiles(abs));
    else if (DOC_EXTENSIONS.some((x) => e.name.endsWith(x))) out.push(abs);
  }
  return out.sort();
}

describe('docs/source does not reference learn/ (ADR-001: Learn Library is separate from Sphinx)', () => {
  it('scanner flags include, :doc:, hyperlink, and toctree entries into learn/ but not prose or component links', () => {
    const planted = [
      'Prose: the lessons live in ``learn/`` and the learn/ directory holds them.',
      '.. include:: ../../learn/backend/http-caching/01-freshness.md',
      'See :doc:`learn/backend/http-caching/02-revalidation`.',
      'Read `the lesson <learn/backend/http-caching/01-freshness.md>`_ first.',
      'See :doc:`components/learn-app` for the component.',
      'External: `RFC <https://example.com/learn/x>`_ is fine.',
      '',
      '.. toctree::',
      '   :maxdepth: 2',
      '',
      '   components/learn-app',
      '   learn/backend/http-caching/01-freshness',
      '',
      'Back to prose.',
    ].join('\n');
    const hits = findLearnLinks(planted);
    expect(hits).toHaveLength(4);
    expect(hits[0]).toContain('.. include:: ../../learn/backend/http-caching/01-freshness.md');
    expect(hits[1]).toContain(':doc:`learn/backend/http-caching/02-revalidation`');
    expect(hits[2]).toContain('<learn/backend/http-caching/01-freshness.md>`_');
    expect(hits[3]).toContain('learn/backend/http-caching/01-freshness');
  });

  it('scans a non-empty set of docs/source files (guards against a vacuous scan)', () => {
    const files = docFiles(DOCS_SOURCE);
    expect(files.length).toBeGreaterThan(10);
    expect(files.some((f) => f.endsWith('index.rst'))).toBe(true);
  });

  it('has no include, link, or toctree entry into learn/ in any file under docs/source', () => {
    const offending: string[] = [];
    for (const file of docFiles(DOCS_SOURCE)) {
      for (const hit of findLearnLinks(readFileSync(file, 'utf8'))) {
        offending.push(`${file.slice(REPO.length + 1)}:${hit}`);
      }
    }
    expect(offending, `docs/source references learn/:\n${offending.join('\n')}`).toEqual([]);
  });
});

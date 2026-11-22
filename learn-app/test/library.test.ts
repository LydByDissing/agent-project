// [origin ref=llm-dsl-p4o5,llm-dsl-gu1y.17,llm-dsl-gu1y.3,llm-dsl-2zv1.18 req=REQ-OPERATOR-EDU-001,REQ-OPERATOR-EDU-002,REQ-OPERATOR-EDU-003 c4=learn_app/lesson_library]
//   [intent]Verifies the lesson library loader and `learn validate` against fixture trees and the real seed learn/ directory.[/intent]
//   [inv]Every validation rule has a failing fixture and a passing positive control.[/inv]
// [/origin]
import { writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { LibraryError, loadLibrary } from '../src/library/load.js';
import { IAC, INDEX, lessonMd, makeLibProject, setMtime, stampedSvg } from './helpers/library.js';

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

const makeProject = makeLibProject;
const lesson = lessonMd;

function expectIssue(fn: () => unknown, ...parts: string[]): string[] {
  let err: unknown;
  try {
    fn();
  } catch (e) {
    err = e;
  }
  expect(err).toBeInstanceOf(LibraryError);
  const issues = (err as LibraryError).issues;
  expect(issues.length).toBeGreaterThan(0);
  const hit = issues.find((i) => parts.every((p) => i.includes(p)));
  expect(hit, `no issue containing ${JSON.stringify(parts)} in ${JSON.stringify(issues)}`).toBeDefined();
  return issues;
}

describe('loadLibrary: tree and prerequisite edges', () => {
  it('returns domain iac, topic terraform-state, two ordered lessons with levels and the edge', () => {
    const lib = loadLibrary(makeProject(IAC));
    expect(lib.domains.map((d) => [d.id, d.title])).toEqual([['iac', 'Infrastructure as code']]);
    const topic = lib.domains[0].topics[0];
    expect(topic.id).toBe('iac/terraform-state');
    expect(topic.title).toBe('Terraform state');
    expect(topic.lessons.map((l) => l.id)).toEqual([
      'iac/terraform-state/01-what-state-is',
      'iac/terraform-state/02-remote-backends',
    ]);
    expect(topic.lessons.map((l) => l.level)).toEqual(['intro', 'working']);
    expect(lib.lessons[1].requires).toEqual(['iac/terraform-state/01-what-state-is']);
    expect(lib.edges).toEqual([{ from: 'iac/terraform-state/02-remote-backends', to: 'iac/terraform-state/01-what-state-is' }]);
    expect(lib.lessons[0].sources).toEqual([{ title: 'Spec', url: 'https://www.rfc-editor.org/rfc/rfc9110#name-etag' }]);
    expect(lib.lessons[0].body).toBe('Body text for the lesson.');
  });

  it('accepts a repo-relative path source with a line number', () => {
    const lib = loadLibrary(
      makeProject({
        ...IAC,
        'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', {
          sources: '  - title: Code\n    path: src/state.py\n    line: 14',
        }),
      }),
    );
    expect(lib.lessons[0].sources).toEqual([{ title: 'Code', path: 'src/state.py', line: 14 }]);
  });
});

describe('loadLibrary: sources (REQ-OPERATOR-EDU-002)', () => {
  it('rejects a lesson with empty sources and names the file', () => {
    const issues = expectIssue(
      () =>
        loadLibrary(
          makeProject({
            ...IAC,
            'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', { sources: '  []' }),
          }),
        ),
      'learn/iac/terraform-state/01-what-state-is.md',
      'sources is empty',
    );
    expect(issues).toHaveLength(1);
  });

  it('rejects a source with neither url nor path and names the entry', () => {
    expectIssue(
      () =>
        loadLibrary(
          makeProject({
            ...IAC,
            'learn/iac/terraform-state/02-remote-backends.md': lesson('iac/terraform-state/02-remote-backends', {
              level: 'working',
              requires: ['iac/terraform-state/01-what-state-is'],
              sources: '  - title: Floating claim',
            }),
          }),
        ),
      'learn/iac/terraform-state/02-remote-backends.md',
      'sources[1] (Floating claim) has neither url nor path',
    );
  });

  it('rejects a source with both url and path', () => {
    expectIssue(
      () =>
        loadLibrary(
          makeProject({
            ...IAC,
            'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', {
              sources: '  - title: Both\n    url: https://example.com/a\n    path: src/a.py',
            }),
          }),
        ),
      'sources[1] (Both) has both url and path',
    );
  });

  it('rejects a path that escapes the project', () => {
    expectIssue(
      () =>
        loadLibrary(
          makeProject({
            ...IAC,
            'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', {
              sources: '  - title: Escape\n    path: ../secrets.txt',
            }),
          }),
        ),
      'sources[1].path must be repo-relative',
    );
  });
});

describe('loadLibrary: prerequisites (REQ-OPERATOR-EDU-001)', () => {
  it('rejects requires naming a missing lesson id', () => {
    expectIssue(
      () =>
        loadLibrary(
          makeProject({
            ...IAC,
            'learn/iac/terraform-state/02-remote-backends.md': lesson('iac/terraform-state/02-remote-backends', {
              level: 'working',
              requires: ['iac/terraform-state/09-missing'],
            }),
          }),
        ),
      'learn/iac/terraform-state/02-remote-backends.md',
      'requires "iac/terraform-state/09-missing"',
    );
  });

  it('rejects a prerequisite cycle and names the cycle', () => {
    expectIssue(
      () =>
        loadLibrary(
          makeProject({
            'learn/iac/index.yaml': INDEX('IaC'),
            'learn/iac/terraform-state/index.yaml': INDEX('State'),
            'learn/iac/terraform-state/01-a.md': lesson('iac/terraform-state/01-a', { requires: ['iac/terraform-state/02-b'] }),
            'learn/iac/terraform-state/02-b.md': lesson('iac/terraform-state/02-b', {
              level: 'working',
              requires: ['iac/terraform-state/01-a'],
            }),
          }),
        ),
      'prerequisite cycle',
      'iac/terraform-state/01-a -> iac/terraform-state/02-b -> iac/terraform-state/01-a',
    );
  });

  it('rejects a lesson that requires itself', () => {
    expectIssue(
      () =>
        loadLibrary(
          makeProject({
            ...IAC,
            'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', {
              requires: ['iac/terraform-state/01-what-state-is'],
            }),
          }),
        ),
      'prerequisite cycle',
    );
  });

  it('accepts a long acyclic chain (positive control for the cycle check)', () => {
    const lib = loadLibrary(
      makeProject({
        'learn/iac/index.yaml': INDEX('IaC'),
        'learn/iac/terraform-state/index.yaml': INDEX('State'),
        'learn/iac/terraform-state/01-a.md': lesson('iac/terraform-state/01-a'),
        'learn/iac/terraform-state/02-b.md': lesson('iac/terraform-state/02-b', { level: 'working', requires: ['iac/terraform-state/01-a'] }),
        'learn/iac/terraform-state/03-c.md': lesson('iac/terraform-state/03-c', {
          level: 'deep',
          requires: ['iac/terraform-state/01-a', 'iac/terraform-state/02-b'],
        }),
      }),
    );
    expect(lib.edges).toHaveLength(3);
  });
});

describe('loadLibrary: diagrams (REQ-OPERATOR-EDU-003)', () => {
  const body = 'See the flow: ![flow](diagrams/state-flow.svg)';
  const withDiagram = (extra: Record<string, string>) => ({
    ...IAC,
    'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', { body }),
    'learn/iac/terraform-state/diagrams/state-flow.puml': '@startuml\n@enduml\n',
    ...extra,
  });

  it('rejects a referenced SVG that is missing', () => {
    const root = makeProject(withDiagram({}));
    expectIssue(
      () => loadLibrary(root),
      'learn/iac/terraform-state/01-what-state-is.md',
      'diagrams/state-flow.svg, which is missing',
    );
  });

  it('rejects a referenced SVG that has no sdd-source-sha256 stamp', () => {
    const root = makeProject(withDiagram({ 'learn/iac/terraform-state/diagrams/state-flow.svg': '<svg/>' }));
    expectIssue(
      () => loadLibrary(root),
      'learn/iac/terraform-state/01-what-state-is.md',
      'diagrams/state-flow.svg has no sdd-source-sha256 stamp',
    );
  });

  it('rejects a referenced SVG whose stamp is a hash of different bytes', () => {
    const root = makeProject(withDiagram({ 'learn/iac/terraform-state/diagrams/state-flow.svg': stampedSvg('@startuml\n@enduml\n!other\n') }));
    expectIssue(() => loadLibrary(root), 'diagrams/state-flow.svg is out of date');
  });

  it('rejects a stamped SVG after one byte of its source changes', () => {
    const original = '@startuml\n@enduml\n';
    const root = makeProject(withDiagram({ 'learn/iac/terraform-state/diagrams/state-flow.svg': stampedSvg(original) }));
    expect(loadLibrary(root).lessons).toHaveLength(2);
    writeFileSync(join(root, 'learn/iac/terraform-state/diagrams/state-flow.puml'), '@startuml\n@enduml\n ');
    expectIssue(() => loadLibrary(root), 'diagrams/state-flow.svg is out of date');
  });

  it('accepts a stamped SVG whose mtime is older than its source (mtimes are ignored)', () => {
    const root = makeProject(withDiagram({ 'learn/iac/terraform-state/diagrams/state-flow.svg': stampedSvg('@startuml\n@enduml\n') }));
    setMtime(root, 'learn/iac/terraform-state/diagrams/state-flow.svg', new Date('2026-01-01T00:00:00Z'));
    setMtime(root, 'learn/iac/terraform-state/diagrams/state-flow.puml', new Date('2026-06-01T00:00:00Z'));
    expect(loadLibrary(root).lessons).toHaveLength(2);
  });

  it('accepts a stamped SVG whose mtime is newer than its source (positive control)', () => {
    const root = makeProject(withDiagram({ 'learn/iac/terraform-state/diagrams/state-flow.svg': stampedSvg('@startuml\n@enduml\n') }));
    setMtime(root, 'learn/iac/terraform-state/diagrams/state-flow.puml', new Date('2026-01-01T00:00:00Z'));
    setMtime(root, 'learn/iac/terraform-state/diagrams/state-flow.svg', new Date('2026-06-01T00:00:00Z'));
    expect(loadLibrary(root).lessons).toHaveLength(2);
  });

  it('rejects a referenced SVG with no source file at all', () => {
    const root = makeProject({
      ...IAC,
      'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', { body }),
      'learn/iac/terraform-state/diagrams/state-flow.svg': '<svg/>',
    });
    expectIssue(() => loadLibrary(root), 'no diagrams/state-flow.puml, .d2 or .mmd source exists');
  });
});

describe('loadLibrary: structure and front matter', () => {
  it('rejects a front matter id that does not match its path', () => {
    expectIssue(
      () =>
        loadLibrary(
          makeProject({
            ...IAC,
            'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/wrong'),
          }),
        ),
      'learn/iac/terraform-state/01-what-state-is.md',
      'id is "iac/terraform-state/wrong" but the file path says "iac/terraform-state/01-what-state-is"',
    );
  });

  it('rejects an unknown level', () => {
    expectIssue(
      () =>
        loadLibrary(
          makeProject({
            ...IAC,
            'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is', { level: 'expert' }),
          }),
        ),
      'level must be one of intro, working, deep',
    );
  });

  it('rejects a file without front matter', () => {
    expectIssue(
      () => loadLibrary(makeProject({ ...IAC, 'learn/iac/terraform-state/01-what-state-is.md': '# just text\n' })),
      'learn/iac/terraform-state/01-what-state-is.md',
      'missing YAML front matter',
    );
  });

  it('rejects a lesson file name that is not NN-slug.md', () => {
    expectIssue(
      () => loadLibrary(makeProject({ ...IAC, 'learn/iac/terraform-state/what.md': lesson('iac/terraform-state/what') })),
      'learn/iac/terraform-state/what.md',
      'file name must be NN-slug.md',
    );
  });

  it('rejects a topic without index.yaml', () => {
    expectIssue(
      () =>
        loadLibrary(
          makeProject({
            'learn/iac/index.yaml': INDEX('IaC'),
            'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is'),
          }),
        ),
      'learn/iac/terraform-state/index.yaml: index.yaml is missing',
    );
  });

  it('rejects a domain without index.yaml', () => {
    expectIssue(
      () => loadLibrary(makeProject({ 'learn/iac/terraform-state/01-what-state-is.md': lesson('iac/terraform-state/01-what-state-is') })),
      'learn/iac/index.yaml: index.yaml is missing',
    );
  });

  it('rejects a missing learn/ directory and names it', () => {
    expectIssue(() => loadLibrary(makeProject({ 'README.md': 'x' })), 'learn/: directory not found');
  });
});

describe('seed learn/ in this repo', () => {
  it('passes validation', () => {
    const lib = loadLibrary(REPO);
    expect(lib.domains.map((d) => d.id)).toEqual(['backend', 'security']);
    expect(lib.domains[0].topics.map((t) => t.id)).toEqual(['backend/http-caching']);
    expect(lib.domains[1].topics.map((t) => t.id)).toEqual(['security/threat-modeling']);
    expect(lib.lessons.map((l) => l.id)).toEqual([
      'backend/http-caching/01-freshness',
      'backend/http-caching/02-revalidation',
      'security/threat-modeling/01-stride',
    ]);
    expect(lib.lessons[1].diagrams).toEqual(['revalidation']);
    expect(lib.edges).toEqual([{ from: 'backend/http-caching/02-revalidation', to: 'backend/http-caching/01-freshness' }]);
  });
});

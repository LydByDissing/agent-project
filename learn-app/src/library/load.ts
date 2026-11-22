// [origin ref=llm-dsl-gu1y.3 req=REQ-OPERATOR-EDU-001,REQ-OPERATOR-EDU-002,REQ-OPERATOR-EDU-003 c4=learn_app/lesson_library]
//   [intent]Loads <project>/learn into a typed domain/topic/lesson tree and rejects any problem by naming the file and the fault.[/intent]
//   [inv]loadLibrary returns a Library only when no problem was found; otherwise it throws LibraryError listing every problem.[/inv]
// [/origin]
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';
import { parse as parseYaml } from 'yaml';
import { type Level, type SourceRef, parseLesson } from './frontmatter.js';

export interface Lesson {
  id: string;
  domain: string;
  topic: string;
  order: number;
  file: string;
  title: string;
  level: Level;
  requires: string[];
  sources: SourceRef[];
  updated: string;
  stale: boolean;
  body: string;
  diagrams: string[];
}

export interface Topic {
  id: string;
  domain: string;
  slug: string;
  title: string;
  summary: string;
  lessons: Lesson[];
}

export interface Domain {
  id: string;
  title: string;
  summary: string;
  topics: Topic[];
}

export interface Library {
  domains: Domain[];
  lessons: Lesson[];
  edges: Array<{ from: string; to: string }>;
}

export class LibraryError extends Error {
  constructor(readonly issues: string[]) {
    super(issues.join('\n'));
    this.name = 'LibraryError';
  }
}

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const LESSON_FILE = /^(\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$/;
const DIAGRAM_REF = /diagrams\/([A-Za-z0-9_.-]+)\.svg/g;
const DIAGRAM_SOURCES = ['puml', 'd2', 'mmd'] as const;

interface Index {
  title: string;
  summary: string;
}

function listDirs(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort();
}

function listFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile())
    .map((e) => e.name)
    .sort();
}

export function loadLibrary(projectDir: string): Library {
  const root = resolve(projectDir);
  const learnDir = join(root, 'learn');
  const issues: string[] = [];
  const rel = (p: string): string => relative(root, p).split(sep).join('/');

  if (!existsSync(learnDir) || !statSync(learnDir).isDirectory()) {
    throw new LibraryError([`learn/: directory not found under ${root}`]);
  }

  const readIndex = (dir: string, what: string): Index | undefined => {
    const file = join(dir, 'index.yaml');
    const label = rel(file);
    if (!existsSync(file)) {
      issues.push(`${label}: index.yaml is missing (every ${what} needs a title and summary)`);
      return undefined;
    }
    let raw: unknown;
    try {
      raw = parseYaml(readFileSync(file, 'utf8'));
    } catch (err) {
      issues.push(`${label}: not valid YAML: ${(err as Error).message.split('\n')[0]}`);
      return undefined;
    }
    const obj = (typeof raw === 'object' && raw !== null && !Array.isArray(raw) ? raw : {}) as Record<string, unknown>;
    let ok = true;
    if (typeof obj.title !== 'string' || obj.title.trim() === '') {
      issues.push(`${label}: title is missing or empty`);
      ok = false;
    }
    if (typeof obj.summary !== 'string' || obj.summary.trim() === '') {
      issues.push(`${label}: summary is missing or empty`);
      ok = false;
    }
    return ok ? { title: obj.title as string, summary: obj.summary as string } : undefined;
  };

  const lessons: Lesson[] = [];
  const domains: Domain[] = [];
  const onDisk = new Set<string>();
  const misplaced = (file: string): string => `${rel(file)}: lessons must live at learn/<domain>/<topic>/NN-slug.md`;

  for (const f of listFiles(learnDir).filter((x) => x.endsWith('.md'))) issues.push(misplaced(join(learnDir, f)));

  for (const domainSlug of listDirs(learnDir)) {
    const domainDir = join(learnDir, domainSlug);
    if (!SLUG.test(domainSlug)) issues.push(`${rel(domainDir)}: directory name must be a lowercase slug`);
    const domainIndex = readIndex(domainDir, 'domain');
    const topics: Topic[] = [];

    for (const f of listFiles(domainDir).filter((x) => x.endsWith('.md'))) issues.push(misplaced(join(domainDir, f)));
    if (listDirs(domainDir).length === 0) issues.push(`${rel(domainDir)}: domain has no topics`);

    for (const topicSlug of listDirs(domainDir)) {
      const topicDir = join(domainDir, topicSlug);
      const topicId = `${domainSlug}/${topicSlug}`;
      if (!SLUG.test(topicSlug)) issues.push(`${rel(topicDir)}: directory name must be a lowercase slug`);
      const topicIndex = readIndex(topicDir, 'topic');
      const topicLessons: Lesson[] = [];
      const seenOrder = new Map<number, string>();
      let lessonFiles = 0;

      for (const sub of listDirs(topicDir).filter((d) => d !== 'diagrams')) {
        issues.push(`${rel(join(topicDir, sub))}: unexpected directory (a topic holds lessons, index.yaml and diagrams/)`);
      }

      for (const f of listFiles(topicDir)) {
        if (f === 'index.yaml' || !f.endsWith('.md')) continue;
        const file = join(topicDir, f);
        const label = rel(file);
        const m = LESSON_FILE.exec(f);
        if (!m) {
          issues.push(`${label}: file name must be NN-slug.md (two-digit order, lowercase slug)`);
          continue;
        }
        lessonFiles++;
        const order = Number(m[1]);
        const id = `${topicId}/${f.slice(0, -3)}`;
        onDisk.add(id);
        if (seenOrder.has(order)) {
          issues.push(`${label}: order ${m[1]} is already used by ${seenOrder.get(order)}`);
          continue;
        }
        seenOrder.set(order, label);

        const parsed = parseLesson(readFileSync(file, 'utf8'), id);
        if (!parsed.value) {
          for (const p of parsed.problems) issues.push(`${label}: ${p}`);
          continue;
        }
        const diagrams = referencedDiagrams(parsed.value.body);
        for (const name of diagrams) {
          const diagramProblem = checkDiagram(join(topicDir, 'diagrams'), name);
          if (diagramProblem) issues.push(`${label}: ${diagramProblem}`);
        }
        topicLessons.push({
          ...parsed.value.meta,
          domain: domainSlug,
          topic: topicSlug,
          order,
          file: label,
          body: parsed.value.body,
          diagrams,
        });
      }

      if (lessonFiles === 0) issues.push(`${rel(topicDir)}: topic has no lessons`);
      topicLessons.sort((a, b) => a.order - b.order);
      lessons.push(...topicLessons);
      if (topicIndex) {
        topics.push({ id: topicId, domain: domainSlug, slug: topicSlug, title: topicIndex.title, summary: topicIndex.summary, lessons: topicLessons });
      }
    }

    if (domainIndex) domains.push({ id: domainSlug, title: domainIndex.title, summary: domainIndex.summary, topics });
  }

  const byId = new Map(lessons.map((l) => [l.id, l]));
  const edges: Array<{ from: string; to: string }> = [];
  for (const l of lessons) {
    for (const r of l.requires) {
      if (!onDisk.has(r)) {
        issues.push(`${l.file}: requires "${r}", which is not a lesson under learn/`);
      } else if (byId.has(r)) {
        edges.push({ from: l.id, to: r });
      }
    }
  }

  issues.push(...findCycles(lessons, byId));

  if (issues.length > 0) throw new LibraryError(issues);

  return { domains, lessons, edges };
}

function referencedDiagrams(body: string): string[] {
  const names = new Set<string>();
  for (const m of body.matchAll(DIAGRAM_REF)) names.add(m[1]);
  return [...names].sort();
}

function checkDiagram(diagramDir: string, name: string): string | undefined {
  const svg = join(diagramDir, `${name}.svg`);
  const sources = DIAGRAM_SOURCES.map((ext) => join(diagramDir, `${name}.${ext}`)).filter((p) => existsSync(p));
  const svgRel = `diagrams/${name}.svg`;
  if (sources.length === 0) {
    return `references ${svgRel}, but no diagrams/${name}.puml, .d2 or .mmd source exists`;
  }
  if (!existsSync(svg)) {
    return `references ${svgRel}, which is missing (render it from ${sources.map((s) => `diagrams/${s.split(sep).pop()}`).join(' or ')})`;
  }
  const svgTime = statSync(svg).mtimeMs;
  const newest = sources.reduce((best, s) => (statSync(s).mtimeMs > statSync(best).mtimeMs ? s : best));
  if (statSync(newest).mtimeMs > svgTime) {
    return `${svgRel} is older than its source diagrams/${newest.split(sep).pop()}; re-render it`;
  }
  return undefined;
}

function findCycles(lessons: Lesson[], byId: Map<string, Lesson>): string[] {
  const out: string[] = [];
  const state = new Map<string, 'open' | 'done'>();
  const stack: string[] = [];

  const visit = (id: string): void => {
    state.set(id, 'open');
    stack.push(id);
    for (const r of byId.get(id)?.requires ?? []) {
      if (!byId.has(r)) continue;
      const s = state.get(r);
      if (s === 'open') {
        const cycle = [...stack.slice(stack.indexOf(r)), r];
        out.push(`${byId.get(r)!.file}: prerequisite cycle ${cycle.join(' -> ')}`);
      } else if (s === undefined) {
        visit(r);
      }
    }
    stack.pop();
    state.set(id, 'done');
  };

  for (const l of lessons) if (!state.has(l.id)) visit(l.id);
  return out;
}

// [origin ref=llm-dsl-gu1y.3 req=REQ-OPERATOR-EDU-001,REQ-OPERATOR-EDU-002,REQ-OPERATOR-EDU-003 c4=learn_app/lesson_library]
//   [intent]Parses a lesson file's YAML front matter and checks each field, returning every problem found rather than the first.[/intent]
//   [inv]parseLesson returns a value only when problems is empty, and every returned source has exactly one of url or path.[/inv]
// [/origin]
import { parse as parseYaml } from 'yaml';

export const LEVELS = ['intro', 'working', 'deep'] as const;
export type Level = (typeof LEVELS)[number];

export interface SourceRef {
  title: string;
  url?: string;
  path?: string;
  line?: number;
}

export interface LessonMeta {
  id: string;
  title: string;
  level: Level;
  requires: string[];
  sources: SourceRef[];
  updated: string;
  stale: boolean;
}

export interface ParsedLesson {
  meta: LessonMeta;
  body: string;
}

export interface ParseResult {
  value?: ParsedLesson;
  problems: string[];
}

const FRONT_MATTER = /^---\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)([\s\S]*)$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function nonEmptyString(v: unknown): v is string {
  return typeof v === 'string' && v.trim() !== '';
}

function parseSource(raw: unknown, n: number, problems: string[]): SourceRef | undefined {
  const at = `sources[${n}]`;
  if (!isRecord(raw)) {
    problems.push(`${at} is not a mapping with title and url or path`);
    return undefined;
  }
  let ok = true;
  if (!nonEmptyString(raw.title)) {
    problems.push(`${at} has no title`);
    ok = false;
  }
  const hasUrl = raw.url !== undefined;
  const hasPath = raw.path !== undefined;
  if (!hasUrl && !hasPath) {
    problems.push(`${at} (${String(raw.title ?? '?')}) has neither url nor path`);
    ok = false;
  } else if (hasUrl && hasPath) {
    problems.push(`${at} (${String(raw.title ?? '?')}) has both url and path; use exactly one`);
    ok = false;
  }
  if (hasUrl) {
    let valid = nonEmptyString(raw.url);
    if (valid) {
      try {
        const u = new URL(raw.url as string);
        valid = u.protocol === 'http:' || u.protocol === 'https:';
      } catch {
        valid = false;
      }
    }
    if (!valid) {
      problems.push(`${at}.url is not an http(s) URL: ${JSON.stringify(raw.url)}`);
      ok = false;
    }
  }
  if (hasPath) {
    const p = raw.path;
    if (!nonEmptyString(p)) {
      problems.push(`${at}.path must be a non-empty string`);
      ok = false;
    } else if (p.startsWith('/') || /^[A-Za-z]:/.test(p) || p.split(/[\\/]/).includes('..')) {
      problems.push(`${at}.path must be repo-relative and stay inside the project: ${JSON.stringify(p)}`);
      ok = false;
    }
  }
  if (raw.line !== undefined && !(Number.isInteger(raw.line) && (raw.line as number) > 0)) {
    problems.push(`${at}.line must be a positive integer: ${JSON.stringify(raw.line)}`);
    ok = false;
  }
  if (!ok) return undefined;
  const src: SourceRef = { title: raw.title as string };
  if (hasUrl) src.url = raw.url as string;
  if (hasPath) src.path = raw.path as string;
  if (raw.line !== undefined) src.line = raw.line as number;
  return src;
}

export function parseLesson(text: string, expectedId: string): ParseResult {
  const problems: string[] = [];
  const m = FRONT_MATTER.exec(text);
  if (!m) {
    return { problems: ['missing YAML front matter (the file must start with a line "---" and close it with another "---")'] };
  }
  const body = m[2].trim();
  if (body === '') problems.push('lesson body is empty');

  let raw: unknown;
  try {
    raw = parseYaml(m[1]);
  } catch (err) {
    return { problems: [...problems, `front matter is not valid YAML: ${(err as Error).message.split('\n')[0]}`] };
  }
  if (!isRecord(raw)) {
    return { problems: [...problems, 'front matter must be a YAML mapping'] };
  }

  if (raw.id !== expectedId) {
    problems.push(`id is ${JSON.stringify(raw.id)} but the file path says ${JSON.stringify(expectedId)}`);
  }
  if (!nonEmptyString(raw.title)) problems.push('title is missing or empty');
  if (!LEVELS.includes(raw.level as Level)) {
    problems.push(`level must be one of ${LEVELS.join(', ')}; found ${JSON.stringify(raw.level)}`);
  }

  let requires: string[] = [];
  if (raw.requires === undefined) {
    problems.push('requires is missing (use [] when there are no prerequisites)');
  } else if (!Array.isArray(raw.requires) || !raw.requires.every(nonEmptyString)) {
    problems.push('requires must be a list of lesson ids');
  } else {
    requires = raw.requires as string[];
  }

  const sources: SourceRef[] = [];
  if (raw.sources === undefined) {
    problems.push('sources is missing (at least one source is required)');
  } else if (!Array.isArray(raw.sources)) {
    problems.push('sources must be a list');
  } else if (raw.sources.length === 0) {
    problems.push('sources is empty (at least one source is required)');
  } else {
    raw.sources.forEach((s, i) => {
      const src = parseSource(s, i + 1, problems);
      if (src) sources.push(src);
    });
  }

  let updated = '';
  if (!(typeof raw.updated === 'string' && ISO_DATE.test(raw.updated) && !Number.isNaN(Date.parse(raw.updated)))) {
    problems.push(`updated must be an ISO date (YYYY-MM-DD); found ${JSON.stringify(raw.updated)}`);
  } else {
    updated = raw.updated;
  }

  if (raw.stale !== undefined && typeof raw.stale !== 'boolean') {
    problems.push(`stale must be true or false; found ${JSON.stringify(raw.stale)}`);
  }

  if (problems.length > 0) return { problems };
  return {
    value: {
      meta: {
        id: expectedId,
        title: raw.title as string,
        level: raw.level as Level,
        requires,
        sources,
        updated,
        stale: raw.stale === true,
      },
      body,
    },
    problems: [],
  };
}

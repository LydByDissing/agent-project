// [origin ref=llm-dsl-gu1y.17 req=REQ-OPERATOR-EDU-007 c4=learn_app/lesson_selector]
//   [intent]Shared in-memory builders for selector tests: lessons, libraries, learners and now.json jobs with a fixed injected today.[/intent]
// [/origin]
import type { Lesson, Library } from '../../src/library/load.js';
import { emptyLearner, type Learner } from '../../src/state/learner.js';

export const TODAY = '2026-11-21';

export function lesson(domain: string, topic: string, order: number, level: Lesson['level'], requires: string[] = []): Lesson {
  const nn = String(order).padStart(2, '0');
  return {
    id: `${domain}/${topic}/${nn}-x`, domain, topic, order, file: '', title: `T ${domain} ${topic} ${nn}`, level, requires,
    sources: [{ title: 's', url: 'https://e.x' }], updated: TODAY, stale: false, body: '', diagrams: [],
  };
}

export const lib = (lessons: Lesson[]): Library => ({ domains: [], lessons, edges: [] });
export const learner = (p: Partial<Learner>): Learner => ({ ...emptyLearner(), ...p });
export const job = (id: string, title: string, topics: string[], status = 'running') => ({ id, title, topics, status });

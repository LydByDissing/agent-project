// [origin ref=llm-dsl-gu1y.5 req=REQ-OPERATOR-EDU-007 c4=learn_app/lesson_selector]
//   [intent]Pins the selector rules: interest filter, prerequisites, box-5 exclusion, ranking, what_changed and determinism.[/intent]
// [/origin]
import { describe, expect, it } from 'vitest';
import type { Lesson, Library } from '../src/library/load.js';
import { type Now, select } from '../src/selector/select.js';
import { emptyLearner, type Learner } from '../src/state/learner.js';

const TODAY = '2026-11-21';

function lesson(domain: string, topic: string, order: number, level: Lesson['level'], requires: string[] = []): Lesson {
  const nn = String(order).padStart(2, '0');
  return {
    id: `${domain}/${topic}/${nn}-x`, domain, topic, order, file: '', title: `T ${domain} ${topic} ${nn}`, level, requires,
    sources: [{ title: 's', url: 'https://e.x' }], updated: TODAY, stale: false, body: '', diagrams: [],
  };
}
const lib = (lessons: Lesson[]): Library => ({ domains: [], lessons, edges: [] });
const learner = (p: Partial<Learner>): Learner => ({ ...emptyLearner(), ...p });
const job = (id: string, topics: string[], status = 'running') => ({ id, title: `job ${id}`, topics, status });

const HTTP1 = lesson('backend', 'http-caching', 1, 'intro');
const HTTP2 = lesson('backend', 'http-caching', 2, 'working', [HTTP1.id]);
const HTTP3 = lesson('backend', 'http-caching', 3, 'deep', [HTTP2.id]);
const L = lib([HTTP1, HTTP2, HTTP3, lesson('frontend', 'css-grid', 1, 'intro'), lesson('iac', 'state', 1, 'intro')]);
const NOW: Now = { jobs: [job('t1', ['backend/http-caching']), job('t4', ['frontend/css-grid'])] };

describe('select', () => {
  it('acceptance example: first http-caching lesson with mastered prerequisites plus what_changed for the skipped topic', () => {
    const l = learner({ interest: { backend: 'deep', frontend: 'skip' } });
    const r = select(L, l, NOW, TODAY);
    expect(r.lesson?.id).toBe(HTTP1.id);
    expect(r.what_changed).toEqual([{ topic: 'frontend/css-grid', interest: 'skip', jobs: [{ id: 't4', title: 'job t4', status: 'running' }] }]);
    expect(r.reason).toContain('t1 job t1');
  });

  it('moves to lesson 2 once lesson 1 is box 3, but not at box 2', () => {
    const base = { interest: { backend: 'deep' as const } };
    const m2 = learner({ ...base, mastery: { [HTTP1.id]: { box: 2, due: '2026-11-30' } } });
    const H = lib([HTTP1, HTTP2, HTTP3]);
    expect(select(H, m2, NOW, TODAY).lesson?.id).toBe(HTTP1.id);
    const m3 = learner({ ...base, mastery: { [HTTP1.id]: { box: 3, due: '2026-11-30' } } });
    expect(select(H, m3, NOW, TODAY).lesson?.id).toBe(HTTP2.id);
  });

  it('basics yields only intro lessons', () => {
    const l = learner({ interest: { backend: 'basics' }, mastery: { [HTTP1.id]: { box: 4, due: '2026-11-30' }, [HTTP2.id]: { box: 4, due: '2026-11-30' } } });
    const r = select(lib([HTTP1, HTTP2, HTTP3]), l, NOW, TODAY);
    expect(r.lesson?.level ?? 'intro').toBe('intro');
    expect(r.lesson?.id).toBe(HTTP1.id);
  });

  it('absent interest behaves as basics', () => {
    const r = select(L, emptyLearner(), { jobs: [] }, TODAY);
    expect(r.lesson?.level).toBe('intro');
  });

  it('topic interest overrides domain interest', () => {
    const l = learner({ interest: { backend: 'deep', 'backend/http-caching': 'skip' } });
    const r = select(lib([HTTP1, HTTP2, HTTP3]), l, NOW, TODAY);
    expect(r.lesson).toBeNull();
    expect(r.what_changed.map((w) => w.topic)).toContain('backend/http-caching');
  });

  it('never returns a box-5 lesson that is not due', () => {
    const only = lib([HTTP1]);
    const l = learner({ interest: { backend: 'deep' }, mastery: { [HTTP1.id]: { box: 5, due: '2026-12-31' } } });
    expect(select(only, l, NOW, TODAY).lesson).toBeNull();
    const due = learner({ interest: { backend: 'deep' }, mastery: { [HTTP1.id]: { box: 5, due: TODAY } } });
    expect(select(only, due, NOW, TODAY).lesson?.id).toBe(HTTP1.id);
  });

  it('with no active topics returns a due review lesson', () => {
    const l = learner({
      interest: { backend: 'deep', iac: 'deep', frontend: 'deep' },
      mastery: {
        [HTTP1.id]: { box: 4, due: '2026-11-30' },
        [HTTP2.id]: { box: 3, due: '2026-11-20' },
        [HTTP3.id]: { box: 5, due: '2027-01-01' },
        'frontend/css-grid/01-x': { box: 5, due: '2027-01-01' },
        'iac/state/01-x': { box: 5, due: '2027-01-01' },
      },
    });
    const r = select(L, l, { jobs: [] }, TODAY);
    expect(r.lesson?.id).toBe(HTTP2.id);
    expect(r.reason).toContain('Due for review');
    expect(r.what_changed).toEqual([]);
  });

  it('active topic outranks a lower-box lesson elsewhere; done jobs are not active', () => {
    const l = learner({ interest: { backend: 'deep', iac: 'deep' }, mastery: { [HTTP1.id]: { box: 3, due: TODAY }, [HTTP2.id]: { box: 3, due: TODAY } } });
    const active = select(L, l, { jobs: [job('t1', ['backend/http-caching'])] }, TODAY);
    expect(active.lesson?.id.startsWith('backend/')).toBe(true);
    const finished = select(L, l, { jobs: [job('t1', ['backend/http-caching'], 'done')] }, TODAY);
    expect(finished.lesson?.id).toBe('frontend/css-grid/01-x'); // new (box 0) beats mastered lessons once nothing is active
  });

  it('ties break by lesson id and result is deterministic and input-order independent', () => {
    const a = lesson('backend', 'a-topic', 1, 'intro');
    const b = lesson('backend', 'b-topic', 1, 'intro');
    const l = learner({ interest: { backend: 'deep' } });
    const r1 = select(lib([b, a]), l, { jobs: [] }, TODAY);
    const r2 = select(lib([a, b]), l, { jobs: [] }, TODAY);
    expect(r1.lesson?.id).toBe(a.id);
    expect(r2).toEqual(r1);
    expect(select(L, l, NOW, TODAY)).toEqual(select(L, l, NOW, TODAY));
  });

  it('does not mutate its inputs', () => {
    const l = learner({ interest: { backend: 'deep' } });
    const snap = JSON.stringify([L, l, NOW]);
    select(L, l, NOW, TODAY);
    expect(JSON.stringify([L, l, NOW])).toBe(snap);
  });
});

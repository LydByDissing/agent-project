// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.6 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/lesson_selector]
//   [intent]Audits the selector against the t3 acceptance criterion on the real seed library, plus interest precedence, skipped-topic notes and the documented rank order.[/intent]
// [/origin]
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { loadLibrary } from '../src/library/load.js';
import { type Now, select } from '../src/selector/select.js';
import { emptyLearner } from '../src/state/learner.js';
import { TODAY, job, learner, lesson, lib } from './helpers/builders.js';

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SEED = loadLibrary(REPO);

describe('select against the seed library (acceptance example)', () => {
  const NOW: Now = {
    jobs: [job('t1', 'Cache headers', ['backend/http-caching']), job('t4', 'Grid layout', ['frontend/css-grid'])],
  };
  const interest = { backend: 'deep' as const, frontend: 'skip' as const };

  it('nothing mastered returns 01-freshness and a what_changed entry for the skipped css-grid job', () => {
    const r = select(SEED, learner({ interest }), NOW, TODAY);
    expect(r.lesson?.id).toBe('backend/http-caching/01-freshness');
    expect(r.what_changed).toEqual([
      { topic: 'frontend/css-grid', interest: 'skip', jobs: [{ id: 't4', title: 'Grid layout', status: 'running' }] },
    ]);
  });

  it('lesson 1 at box 3 hands over to 02-revalidation', () => {
    const r = select(SEED, learner({ interest, mastery: { 'backend/http-caching/01-freshness': { box: 3, due: '2099-01-01' } } }), NOW, TODAY);
    expect(r.lesson?.id).toBe('backend/http-caching/02-revalidation');
  });

  it('lesson 1 at box 2 keeps 01-freshness; 02-revalidation is not returned', () => {
    const r = select(SEED, learner({ interest, mastery: { 'backend/http-caching/01-freshness': { box: 2, due: '2099-01-01' } } }), NOW, TODAY);
    expect(r.lesson?.id).toBe('backend/http-caching/01-freshness');
  });

  it('a job on a skipped topic yields no lesson from that topic when it is the only active job', () => {
    const r = select(SEED, learner({ interest }), { jobs: [job('t4', 'Grid layout', ['frontend/css-grid'])] }, TODAY);
    expect(r.lesson?.domain).not.toBe('frontend');
    expect(r.lesson?.id).toBe('backend/http-caching/01-freshness');
  });
});

describe('select what_changed for skipped topics', () => {
  it('lists every running job on a skipped topic with its id, title and status', () => {
    const L = lib([lesson('backend', 'a-topic', 1, 'intro')]);
    const now: Now = {
      jobs: [job('t7', 'Layout pass', ['frontend/css-grid']), job('t8', 'Gap fix', ['frontend/css-grid'], 'queued')],
    };
    const r = select(L, learner({ interest: { frontend: 'skip', backend: 'deep' } }), now, TODAY);
    expect(r.what_changed).toEqual([
      {
        topic: 'frontend/css-grid',
        interest: 'skip',
        jobs: [
          { id: 't7', title: 'Layout pass', status: 'running' },
          { id: 't8', title: 'Gap fix', status: 'queued' },
        ],
      },
    ]);
  });

  it('omits finished jobs from what_changed', () => {
    const r = select(lib([]), learner({ interest: { frontend: 'skip' } }), { jobs: [job('t9', 'Old', ['frontend/css-grid'], 'done')] }, TODAY);
    expect(r.what_changed).toEqual([]);
  });

  it('does not report a basics or deep topic as what_changed', () => {
    const r = select(lib([]), learner({ interest: { frontend: 'basics' } }), { jobs: [job('t4', 'Grid', ['frontend/css-grid'])] }, TODAY);
    expect(r.what_changed).toEqual([]);
  });
});

describe('select interest precedence', () => {
  it('absent interest behaves as basics: an unmastered deep lesson is never returned', () => {
    const L = lib([lesson('backend', 'http', 1, 'intro'), lesson('backend', 'http', 2, 'deep', ['backend/http/01-x'])]);
    const r = select(L, learner({ mastery: { 'backend/http/01-x': { box: 3, due: '2099-01-01' } } }), { jobs: [] }, TODAY);
    expect(r.lesson?.id).toBe('backend/http/01-x');
  });

  it('absent interest is not skip: an intro lesson is still returned', () => {
    const r = select(lib([lesson('backend', 'http', 1, 'intro')]), emptyLearner(), { jobs: [] }, TODAY);
    expect(r.lesson?.id).toBe('backend/http/01-x');
  });

  it('topic skip overrides domain deep, while a sibling topic in the same domain is still returned', () => {
    const L = lib([lesson('backend', 'http-caching', 1, 'intro'), lesson('backend', 'queues', 1, 'intro')]);
    const now: Now = { jobs: [job('t1', 'Cache headers', ['backend/http-caching'])] };
    const r = select(L, learner({ interest: { backend: 'deep', 'backend/http-caching': 'skip' } }), now, TODAY);
    expect(r.lesson?.id).toBe('backend/queues/01-x');
    expect(r.what_changed).toEqual([
      { topic: 'backend/http-caching', interest: 'skip', jobs: [{ id: 't1', title: 'Cache headers', status: 'running' }] },
    ]);
  });
});

describe('select rank order: active, due, lowest box, lesson order, id', () => {
  it('active topic beats an overdue lesson on a non-active topic', () => {
    const L = lib([lesson('backend', 'http-caching', 1, 'intro'), lesson('iac', 'state', 1, 'intro')]);
    const l = learner({
      interest: { backend: 'deep', iac: 'deep' },
      mastery: {
        'backend/http-caching/01-x': { box: 4, due: '2099-01-01' },
        'iac/state/01-x': { box: 2, due: '2026-11-01' },
      },
    });
    const r = select(L, l, { jobs: [job('t1', 'Cache headers', ['backend/http-caching'])] }, TODAY);
    expect(r.lesson?.id).toBe('backend/http-caching/01-x');
  });

  it('an overdue lesson beats a not-due lesson even when the not-due one has a lower box', () => {
    const L = lib([lesson('backend', 'a-topic', 1, 'intro'), lesson('backend', 'b-topic', 1, 'intro')]);
    const l = learner({
      interest: { backend: 'deep' },
      mastery: {
        'backend/a-topic/01-x': { box: 2, due: '2026-11-01' },
        'backend/b-topic/01-x': { box: 0, due: '2099-01-01' },
      },
    });
    const r = select(L, l, { jobs: [] }, TODAY);
    expect(r.lesson?.id).toBe('backend/a-topic/01-x');
    expect(r.reason).toContain('Due for review');
  });

  it('lower box wins among lessons with equal due state', () => {
    const L = lib([lesson('backend', 'a-topic', 1, 'intro'), lesson('backend', 'b-topic', 1, 'intro')]);
    const l = learner({
      interest: { backend: 'deep' },
      mastery: {
        'backend/a-topic/01-x': { box: 2, due: '2099-01-01' },
        'backend/b-topic/01-x': { box: 1, due: '2099-01-01' },
      },
    });
    expect(select(L, l, { jobs: [] }, TODAY).lesson?.id).toBe('backend/b-topic/01-x');
  });

  it('lesson order beats id: order 1 in a later-sorting domain wins over order 2 in an earlier one', () => {
    const L = lib([lesson('aaa', 'topic', 2, 'intro'), lesson('zzz', 'topic', 1, 'intro')]);
    const r = select(L, learner({ interest: { aaa: 'deep', zzz: 'deep' } }), { jobs: [] }, TODAY);
    expect(r.lesson?.id).toBe('zzz/topic/01-x');
  });
});

describe('select determinism', () => {
  it('same inputs give a deep-equal selection object on repeated calls', () => {
    const now: Now = { jobs: [job('t1', 'Cache headers', ['backend/http-caching']), job('t4', 'Grid', ['frontend/css-grid'])] };
    const l = learner({ interest: { backend: 'deep', frontend: 'skip' }, mastery: { 'backend/http-caching/01-freshness': { box: 1, due: '2026-11-25' } } });
    const first = select(SEED, l, now, TODAY);
    const second = select(SEED, l, now, TODAY);
    expect(first.lesson).not.toBeNull();
    expect(JSON.stringify(second)).toBe(JSON.stringify(first));
    expect(second).toEqual(first);
  });

  it('the reason text names the running job when an active topic drives the choice', () => {
    const now: Now = { jobs: [job('t1', 'Cache headers', ['backend/http-caching'])] };
    const r = select(SEED, learner({ interest: { backend: 'deep' } }), now, TODAY);
    expect(r.reason).toBe('Shown because t1 Cache headers is running now on backend/http-caching, and your interest in backend/http-caching is deep.');
  });
});

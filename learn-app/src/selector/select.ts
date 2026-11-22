// [origin ref=llm-dsl-gu1y.5 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/lesson_selector]
//   [intent]Pure function choosing the next lesson from library, learner state, run status and today's date, plus notes on skipped active topics.[/intent]
//   [inv]select does no IO and never reads the clock; the same inputs always give the same result.[/inv]
// [/origin]
import type { Lesson, Library } from '../library/load.js';
import type { Interest, Learner } from '../state/learner.js';

export interface NowJob {
  id: string;
  title: string;
  topics: string[];
  status: string;
}

export interface Now {
  jobs: NowJob[];
}

export interface WhatChanged {
  topic: string;
  interest: Interest;
  jobs: Array<{ id: string; title: string; status: string }>;
}

export interface Selection {
  lesson: Lesson | null;
  reason: string;
  what_changed: WhatChanged[];
}

export const MASTERED_BOX = 3;
export const MAX_BOX = 5;
const INACTIVE = new Set(['done', 'failed']);

export function interestFor(learner: Learner, domain: string, topic?: string): Interest {
  return (topic ? learner.interest[`${domain}/${topic}`] : undefined) ?? learner.interest[domain] ?? 'basics';
}

export function activeJobs(now: Now): NowJob[] {
  return now.jobs.filter((j) => !INACTIVE.has(j.status));
}

export function prerequisitesMet(lesson: Lesson, learner: Learner): boolean {
  return lesson.requires.every((r) => (learner.mastery[r]?.box ?? 0) >= MASTERED_BOX);
}

export function visibleAtInterest(lesson: Lesson, interest: Interest): boolean {
  if (interest === 'skip') return false;
  return interest === 'deep' || lesson.level === 'intro';
}

export function select(library: Library, learner: Learner, now: Now, today: string): Selection {
  const jobs = activeJobs(now);
  const jobsByTopic = new Map<string, NowJob[]>();
  for (const j of jobs) for (const t of j.topics) jobsByTopic.set(t, [...(jobsByTopic.get(t) ?? []), j]);

  const what_changed: WhatChanged[] = [...jobsByTopic.keys()]
    .sort()
    .flatMap((topic) => {
      const [domain, slug] = topic.split('/');
      const interest = interestFor(learner, domain, slug);
      if (interest !== 'skip') return [];
      return [{ topic, interest, jobs: jobsByTopic.get(topic)!.map(({ id, title, status }) => ({ id, title, status })) }];
    });

  interface Candidate {
    lesson: Lesson;
    active: boolean;
    due: boolean;
    box: number;
  }
  const candidates: Candidate[] = [];
  for (const lesson of library.lessons) {
    if (!visibleAtInterest(lesson, interestFor(learner, lesson.domain, lesson.topic))) continue;
    if (!prerequisitesMet(lesson, learner)) continue;
    const m = learner.mastery[lesson.id];
    if (m && m.box >= MAX_BOX && m.due > today) continue;
    candidates.push({
      lesson,
      active: jobsByTopic.has(`${lesson.domain}/${lesson.topic}`),
      due: !m || m.due <= today,
      box: m?.box ?? 0,
    });
  }

  candidates.sort(
    (a, b) =>
      Number(b.active) - Number(a.active) ||
      Number(b.due) - Number(a.due) ||
      a.box - b.box ||
      a.lesson.order - b.lesson.order ||
      (a.lesson.id < b.lesson.id ? -1 : a.lesson.id > b.lesson.id ? 1 : 0),
  );

  const top = candidates[0];
  if (!top) return { lesson: null, reason: 'No lesson is available for your interests and progress right now.', what_changed };

  const topic = `${top.lesson.domain}/${top.lesson.topic}`;
  const interest = interestFor(learner, top.lesson.domain, top.lesson.topic);
  let reason: string;
  if (top.active) {
    const running = jobsByTopic.get(topic)!.map((j) => `${j.id} ${j.title}`).join(' and ');
    reason = `Shown because ${running} ${jobsByTopic.get(topic)!.length === 1 ? 'is' : 'are'} running now on ${topic}, and your interest in ${topic} is ${interest}.`;
  } else if (!learner.mastery[top.lesson.id]) {
    reason = `No running job needs a lesson, so here is the next new lesson in ${topic} (interest ${interest}).`;
  } else if (top.due) {
    reason = `Due for review: box ${top.box}, due ${learner.mastery[top.lesson.id].due}.`;
  } else {
    reason = `Nothing is due, so here is the lowest-box lesson in ${topic} (box ${top.box}).`;
  }
  return { lesson: top.lesson, reason, what_changed };
}

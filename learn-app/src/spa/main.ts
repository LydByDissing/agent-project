// [origin ref=llm-dsl-gu1y.9,llm-dsl-gu1y.5,llm-dsl-gu1y.7 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-006,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-008,REQ-OPERATOR-EDU-009,REQ-OPERATOR-EDU-010 c4=learn_app/learn_spa]
//   [intent]Renders the wave strip, topic tree, lesson with its live quiz, the interest onboarding and settings view, and the more-like-this / basics / not-for-me controls, all from the JSON API.[/intent]
//   [inv]The SPA only talks to the server's JSON API; Markdown HTML is escaped, never injected raw; an empty interest map on load always routes to the onboarding view.[/inv]
// [/origin]
import { Marked } from 'marked';
import './style.css';

interface Job { id: string; title: string; topics: string[]; status: string }
interface NowDoc { run?: string; wave?: number; jobs: Job[] }
interface Mastery { box: number; due: string }
interface TreeLesson { id: string; title: string; level: string; order: number; mastery: Mastery | null; status: string }
interface TreeTopic { id: string; title: string; interest: string; lessons: TreeLesson[] }
interface TreeDomain { id: string; title: string; interest: string; topics: TreeTopic[] }
interface Source { title: string; url?: string; path?: string; line?: number }
interface LessonDoc {
  id: string; title: string; level: string; domain: string; topic: string; topic_title: string;
  topic_position: number; topic_size: number; requires: Array<{ id: string; title: string; mastered: boolean }>;
  sources: Source[]; updated: string; body: string;
}
type Interest = 'deep' | 'basics' | 'skip';
interface InterestDoc { interest: Record<string, Interest>; domains: Array<{ id: string; title: string; topics: Array<{ id: string; title: string }> }> }
interface NextDoc { lesson: { id: string } | null; reason: string; what_changed: Array<{ topic: string; jobs: Array<{ id: string; title: string; status: string }> }> }

const $ = (id: string): HTMLElement => document.getElementById(id) as HTMLElement;
const esc = (s: string): string => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
const safeHref = (h: string): string => (/^(https?:|mailto:|#|\/)/i.test(h) ? h : '#');

function assetUrl(lesson: LessonDoc, src: string): string {
  const clean = src.replace(/^\.\//, '');
  return `/api/asset/${lesson.domain}/${lesson.topic}/${clean}`.replace(/\/+/g, '/');
}

function renderMarkdown(lesson: LessonDoc): string {
  const md = new Marked({
    renderer: {
      html: ({ text }) => esc(text),
      link({ href, title, tokens }) {
        const t = title ? ` title="${esc(title)}"` : '';
        return `<a href="${esc(safeHref(href))}"${t} target="_blank" rel="noopener">${this.parser.parseInline(tokens)}</a>`;
      },
      image({ href, text }) {
        return `<img src="${esc(assetUrl(lesson, href))}" alt="${esc(text)}">`;
      },
    },
  });
  return md.parse(lesson.body, { async: false }) as string;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return (await res.json()) as T;
}

function boxes(n: number): string {
  return `<span class="boxes" aria-label="box ${n} of 5">${[1, 2, 3, 4, 5].map((i) => `<i class="${i <= n ? 'on' : ''}"></i>`).join('')}</span>`;
}

let current: string | null = null;
let nextDoc: NextDoc | null = null;
let nowDoc: NowDoc = { jobs: [] };
let tree: TreeDomain[] = [];
let interests: InterestDoc | null = null;
let currentDoc: LessonDoc | null = null;
let firstRun = false;
let toastTimer: number | undefined;

function renderWave(): void {
  const jobs = nowDoc.jobs;
  if (jobs.length === 0) {
    $('wave').innerHTML = '<span class="label">No wave running</span>';
    $('banner').hidden = true;
    return;
  }
  const started = jobs.filter((j) => j.status !== 'queued');
  const done = started.filter((j) => j.status === 'done' || j.status === 'failed').length;
  const wave = nowDoc.wave === undefined ? '' : `Wave ${nowDoc.wave} · `;
  $('wave').innerHTML =
    `<span class="label" title="${esc(nowDoc.run ? `run ${nowDoc.run}` : '')}">${wave}${done}/${started.length} done</span>` +
    jobs.map((j) => `<span class="job" data-s="${esc(j.status)}" title="${esc(j.title)}"><span class="dot"></span><span class="t">${esc(j.id)} ${esc(j.title)}</span><span class="tp">${esc(j.status)}</span></span>`).join('');
  const finished = started.length > 0 && !started.some((j) => j.status === 'running');
  $('banner').hidden = !finished;
  $('banner-text').textContent = `${nowDoc.wave === undefined ? 'Wave' : `Wave ${nowDoc.wave}`} finished. Agents are waiting for you in the terminal.`;
}

function renderTree(): void {
  $('tree').innerHTML = tree.map((d) => {
    const topics = d.topics.map((t) => {
      const rows = t.lessons.map((l) => {
        const dim = ['skipped', 'not_at_basics', 'locked'].includes(l.status);
        const right = l.status === 'skipped' ? '<span class="tp mono" style="font-size:11px">skipped</span>'
          : l.status === 'not_at_basics' ? '<span class="tp mono" style="font-size:11px">not at basics</span>'
          : l.mastery ? boxes(l.mastery.box)
          : `<span class="mono" style="font-size:11px">${l.status === 'locked' ? 'locked' : 'new'}</span>`;
        const label = `${String(l.order).padStart(2, '0')} ${esc(l.title)}`;
        const name = dim ? `<span class="nm">${label}</span>` : `<a class="nm" href="#lesson/${esc(l.id)}" style="text-decoration:none;color:inherit">${label}</a>`;
        return `<div class="ls ${l.id === current ? 'cur' : ''} ${dim ? 'locked' : ''}">${name}${right}</div>`;
      }).join('');
      return `<div class="topic"><span class="tn">${esc(t.id.split('/')[1])}</span>${rows}</div>`;
    }).join('');
    return `<div class="dom ${d.interest === 'skip' ? 'skip' : ''}"><div class="dom-h"><b>${esc(d.title)}</b><span class="pill" data-i="${esc(d.interest)}">${esc(d.interest)}</span></div>${topics}</div>`;
  }).join('');
}

function renderChanged(): void {
  const items = nextDoc?.what_changed ?? [];
  $('changed').innerHTML = '<b>What changed in topics you skip</b><br>' + (items.length
    ? items.map((w) => w.jobs.map((j) => `${esc(w.topic)}: ${esc(j.title)} (${esc(j.id)}, ${esc(j.status)})`).join('<br>')).join('<br>')
    : 'Nothing in this wave.');
}

async function refreshLearnerPeek(): Promise<void> {
  $('statejson').textContent = JSON.stringify(await getJson('/api/learner'), null, 2);
}

function sourceRow(s: Source): string {
  if (s.url) return `<li><a href="${esc(safeHref(s.url))}" target="_blank" rel="noopener">${esc(s.title)}</a><span class="k">link</span></li>`;
  const ref = `${s.path ?? ''}${s.line ? `:${s.line}` : ''}`;
  return `<li>${esc(s.title)} <span class="mono">${esc(ref)}</span><span class="k">this repo</span></li>`;
}

async function showLesson(id: string, why: string): Promise<void> {
  const lesson = await getJson<LessonDoc>(`/api/lesson/${id}`);
  current = lesson.id;
  currentDoc = lesson;
  firstRun = false;
  const reqs = lesson.requires.length
    ? `<span>requires ${lesson.requires.map((r) => `<a href="#lesson/${esc(r.id)}">${esc(r.title)}</a> · ${r.mastered ? 'mastered' : 'not yet mastered'}`).join(', ')}</span>` : '';
  $('app').innerHTML = `
    <div class="crumbs"><span class="chip">${esc(lesson.domain)} / ${esc(lesson.topic)} / ${String(lesson.topic_position).padStart(2, '0')}</span><span class="chip lv">${esc(lesson.level)}</span>${reqs}<span>· updated ${esc(lesson.updated)}</span></div>
    <div class="why">${esc(why)}</div>
    <article class="lesson">
      <h1>${esc(lesson.title)}</h1>
      <p class="sub">Lesson ${lesson.topic_position} of ${lesson.topic_size} in ${esc(lesson.topic_title)}.</p>
      <div class="prose" id="prose">${renderMarkdown(lesson)}</div>
      <div class="sources"><div class="label">Sources</div><ol>${lesson.sources.map(sourceRow).join('')}</ol></div>
    </article>
    <div class="react" aria-label="How much of this do you want">
      <button class="btn" type="button" data-int="deep">More like this</button>
      <button class="btn" type="button" data-int="basics">Basics are enough</button>
      <button class="btn quiet" type="button" data-int="skip">Not for me</button>
    </div>
    <section class="quiz" id="quiz">
      <div class="qhead"><h2>Check yourself</h2><div class="gen" id="gen"></div></div>
      <div class="persona" id="persona" hidden></div>
      <div id="qs"></div>
      <div id="result" hidden></div>
    </section>`;
  wireDiagrams();
  renderTree();
  void loadQuiz(lesson.id);
}

interface QuizDoc { quizId: string; seconds: number; persona: { box: number; interest: string; misses: string[] }; questions: Array<{ q: string; options: string[] }> }
interface AnswerDoc {
  correct: boolean; correctIndex: number; explanations: string[]; source: Source & { key: string };
  complete: boolean; allCorrect?: boolean; box?: number; due?: string;
}
let quizSeq = 0;

async function loadQuiz(lessonId: string): Promise<void> {
  const seq = ++quizSeq;
  const live = (): boolean => seq === quizSeq && current === lessonId && !!document.getElementById('gen');
  $('gen').innerHTML = '<span><b>●</b> generating</span><span>claude -p is writing your questions while you read</span>';
  $('qs').innerHTML = '';
  $('result').hidden = true;
  $('persona').hidden = true;
  try {
    const res = await fetch(`/api/quiz/${lessonId}`, { method: 'POST' });
    const data = (await res.json()) as QuizDoc & { error?: { name: string; message: string } | string };
    if (!live()) return;
    if (!res.ok) {
      const e = typeof data.error === 'object' ? data.error : { name: 'Error', message: String(data.error ?? res.status) };
      return quizError(lessonId, e.name, e.message);
    }
    $('gen').innerHTML = `<span><b>●</b> ready</span><span>claude -p · generated while you read · ${data.seconds} s</span>`;
    const p = data.persona;
    const misses = p.misses.length ? `, and you missed ${p.misses.map((m) => `<b>"${esc(m)}"</b>`).join(', ')} before, so those come back` : '';
    $('persona').innerHTML = `Written for you: this lesson is in <b>box ${p.box}</b>, this subject is set to <b>${esc(p.interest)}</b>${misses}.`;
    $('persona').hidden = false;
    renderQuestions(data);
  } catch (err) {
    if (live()) quizError(lessonId, (err as Error).name, (err as Error).message);
  }
}

function quizError(lessonId: string, name: string, message: string): void {
  $('gen').innerHTML = '<span><b>●</b> error</span>';
  $('qs').innerHTML = `<div class="result bad"><span><b>${esc(name)}</b>: ${esc(message)}</span><button type="button" class="btn" id="retry">Retry</button></div>`;
  $('retry').addEventListener('click', () => void loadQuiz(lessonId));
}

function renderQuestions(quiz: QuizDoc): void {
  const n = quiz.questions.length;
  $('qs').innerHTML = quiz.questions.map((q, qi) => `<div class="q" data-q="${qi}"><h3><span class="n">${qi + 1}/${n}</span>${esc(q.q)}</h3><div class="opts">${
    q.options.map((o, oi) => `<button type="button" class="opt" data-q="${qi}" data-o="${oi}"><span class="key">${'ABCDE'[oi]}</span><span>${esc(o)}</span></button>`).join('')}</div></div>`).join('');
  $('qs').onclick = (e) => {
    const b = (e.target as HTMLElement).closest('.opt') as HTMLButtonElement | null;
    if (!b || b.disabled) return;
    const qi = Number(b.dataset.q);
    const group = b.closest('.opts') as HTMLElement;
    group.querySelectorAll<HTMLButtonElement>('.opt').forEach((x) => (x.disabled = true));
    void answer(quiz.quizId, qi, Number(b.dataset.o), group);
  };
}

async function answer(quizId: string, qi: number, chosen: number, group: HTMLElement): Promise<void> {
  const unlock = (): void => group.querySelectorAll<HTMLButtonElement>('.opt').forEach((x) => (x.disabled = false));
  try {
    const res = await fetch('/api/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ quizId, questionIndex: qi, chosen }) });
    const a = (await res.json()) as AnswerDoc & { error?: string };
    if (!res.ok) {
      if (res.status !== 409) unlock();
      $('result').hidden = false;
      $('result').className = 'result bad';
      $('result').textContent = `Could not grade: ${a.error ?? res.status}`;
      return;
    }
    const link = a.source.url ? `<a href="${esc(safeHref(a.source.url))}" target="_blank" rel="noopener">${esc(a.source.title)}</a>` : `<span class="mono">${esc(a.source.title)}</span>`;
    group.querySelectorAll<HTMLElement>('.opt').forEach((x) => {
      const k = Number(x.dataset.o);
      if (k === a.correctIndex) x.classList.add('right');
      else if (k === chosen) x.classList.add('wrong');
      x.insertAdjacentHTML('beforeend', `<span class="ex">${esc(a.explanations[k] ?? '')} ${link}</span>`);
    });
    if (a.complete) {
      const r = $('result');
      r.hidden = false;
      r.className = `result ${a.allCorrect ? 'ok' : 'bad'}`;
      r.innerHTML = (a.allCorrect ? `All correct. Revalidation moves to box ${a.box}. ` : `Not quite. Revalidation drops to box ${a.box} and comes back soon, with new questions on what you missed. `) + `<span class="mono">next review ${esc(a.due ?? '')}</span>`;
    }
    void refreshAfterAnswer();
  } catch (err) {
    unlock();
    $('result').hidden = false;
    $('result').className = 'result bad';
    $('result').textContent = `Could not grade: ${(err as Error).message}`;
  }
}

async function refreshAfterAnswer(): Promise<void> {
  try {
    tree = (await getJson<{ domains: TreeDomain[] }>('/api/tree')).domains;
    renderTree();
    await refreshLearnerPeek();
  } catch {
    // the next lesson open refreshes both
  }
}

function wireDiagrams(): void {
  document.querySelectorAll<HTMLImageElement>('#prose img').forEach((img) => {
    const fig = document.createElement('figure');
    fig.className = 'dia';
    fig.innerHTML = `<div class="dia-bar"><span>${esc(img.getAttribute('src')?.split('/').pop() ?? '')}</span><span><button type="button" data-z="-1" aria-label="Zoom out">−</button> <button type="button" data-z="1" aria-label="Zoom in">+</button></span></div><div class="dia-view"></div><figcaption>${esc(img.alt)}</figcaption>`;
    const view = fig.querySelector('.dia-view') as HTMLElement;
    img.style.cssText = 'display:block;max-width:100%;background:#fff;transform-origin:top left';
    let z = 1;
    fig.addEventListener('click', (e) => {
      const b = (e.target as HTMLElement).closest('button[data-z]') as HTMLElement | null;
      if (!b) return;
      z = Math.min(2.5, Math.max(1, z + 0.25 * Number(b.dataset.z)));
      img.style.transform = `scale(${z})`;
    });
    const target = img.closest('p') ?? img;
    target.replaceWith(fig);
    view.appendChild(img);
  });
}

async function refreshTree(): Promise<void> {
  tree = (await getJson<{ domains: TreeDomain[] }>('/api/tree')).domains;
  renderTree();
}

async function putInterest(body: { key: string; value: Interest }): Promise<void> {
  const res = await fetch('/api/interest', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = (await res.json()) as { interest?: Record<string, Interest>; message?: string; error?: string };
  if (!res.ok) throw new Error(data.message ?? data.error ?? `PUT /api/interest: ${res.status}`);
  if (interests && data.interest) interests.interest = data.interest;
}

function notify(msg: string, bad = false): void {
  const t = $('toast');
  t.textContent = msg;
  t.dataset.bad = String(bad);
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (t.hidden = true), 2600);
}

const seg = (key: string, own: Interest | undefined, label: string): string =>
  `<div class="seg" role="group" aria-label="${esc(label)}">${(['deep', 'basics', 'skip'] as const)
    .map((v) => `<button type="button" data-k="${esc(key)}" data-v="${v}" aria-pressed="${own === v}">${v}</button>`).join('')}</div>`;

function renderInterests(): void {
  if (!interests) return;
  const { interest, domains } = interests;
  const intro = firstRun
    ? '<div class="label">First run · also under Interests at any time</div><h1>What do you want to get better at?</h1>'
    : '<div class="label">Settings</div><h1>Interests</h1>';
  const rows = domains.map((d) => {
    const dv = interest[d.id];
    const topics = d.topics.map((t) => {
      const tv = interest[t.id];
      const note = tv ? 'set for this topic' : `inherits ${dv ?? 'basics'}`;
      return `<div class="irow itopic"><div><span class="mono">${esc(t.title)}</span><small>${esc(note)}</small></div>${seg(t.id, tv, `${t.title} interest`)}</div>`;
    }).join('');
    const dnote = `${dv ? 'set for this domain' : 'not set yet, basics applies'} · ${d.topics.length} topics`;
    return `<section class="idom"><div class="irow"><div><b>${esc(d.title)}</b><small>${esc(dnote)}</small></div>${seg(d.id, dv, `${d.title} interest`)}</div>${topics}</section>`;
  }).join('');
  $('app').innerHTML = `<section class="onb">${intro}
    <p>These domains appear in this project's plan. Deep gets every level, basics stops at intro lessons, and skip never shows lessons, only a one-line note when agents change something there. Your choices are saved in <span class="mono">~/.sdd/learner.json</span> and apply to every project.</p>
    <div id="irows">${rows || '<p>No domains found in learn/.</p>'}</div>
    <div class="react"><a class="btn primary" href="#lesson" style="text-decoration:none">Save and show my next lesson</a></div>
  </section>`;
}

async function showInterests(): Promise<void> {
  interests = await getJson<InterestDoc>('/api/interest');
  renderInterests();
}

async function setInterest(key: string, value: Interest): Promise<void> {
  try {
    await putInterest({ key, value });
    renderInterests();
    await refreshTree();
    notify(`${key} set to ${value}.`);
  } catch (err) {
    notify(`Could not save: ${(err as Error).message}`, true);
  }
}

async function lessonAction(doc: LessonDoc, value: Interest): Promise<void> {
  try {
    await putInterest({ key: `${doc.domain}/${doc.topic}`, value });
  } catch (err) {
    notify(`Could not save: ${(err as Error).message}`, true);
    return;
  }
  notify(
    value === 'deep' ? `${doc.topic_title} set to deep.`
      : value === 'basics' ? `${doc.topic_title} set to basics. Only intro lessons from now on.`
      : `${doc.topic_title} skipped. You'll get a one-line note when agents touch it.`,
  );
  try {
    nextDoc = await getJson<NextDoc>('/api/next');
    await refreshTree();
  } catch (err) {
    fail(err);
    return;
  }
  renderChanged();
  history.replaceState(null, '', nextDoc.lesson ? `#lesson/${nextDoc.lesson.id}` : '#lesson');
  await showNext().catch(fail);
}

function onAppClick(e: Event): void {
  const target = e.target as HTMLElement;
  const k = target.closest('button[data-k]') as HTMLButtonElement | null;
  if (k) {
    void setInterest(k.dataset.k as string, k.dataset.v as Interest);
    return;
  }
  const act = target.closest('button[data-int]') as HTMLButtonElement | null;
  if (act && currentDoc) void lessonAction(currentDoc, act.dataset.int as Interest);
}

function route(): void {
  const onInterests = location.hash === '#interests';
  document.querySelectorAll<HTMLAnchorElement>('nav.nav a').forEach((a) => {
    if (a.dataset.nav === (onInterests ? 'interests' : 'lesson')) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  if (onInterests) {
    currentDoc = null;
    void showInterests().catch(fail);
    return;
  }
  const m = /^#lesson\/(.+)$/.exec(location.hash);
  if (m) void showLesson(decodeURIComponent(m[1]), 'You opened this lesson from the tree.').catch(fail);
  else void showNext().catch(fail);
}

async function showNext(): Promise<void> {
  nextDoc = await getJson<NextDoc>('/api/next');
  renderChanged();
  if (nextDoc.lesson) await showLesson(nextDoc.lesson.id, nextDoc.reason);
  else {
    currentDoc = null;
    $('app').innerHTML = `<div class="why">${esc(nextDoc.reason)}</div>`;
  }
}

function fail(err: unknown): void {
  $('app').innerHTML = `<div class="why">Could not load: ${esc((err as Error).message)}</div>`;
}

async function pollNow(): Promise<void> {
  try {
    const prev = JSON.stringify(nowDoc);
    nowDoc = await getJson<NowDoc>('/api/now');
    renderWave();
    if (nextDoc && JSON.stringify(nowDoc) !== prev) {
      // keep the open lesson stable; only the skipped-topic note follows the run
      nextDoc.what_changed = (await getJson<NextDoc>('/api/next')).what_changed;
      renderChanged();
    }
  } catch {
    // keep the last strip; the next tick retries
  }
}

async function start(): Promise<void> {
  await pollNow();
  setInterval(() => void pollNow(), 2000);
  $('app').addEventListener('click', onAppClick);
  try {
    const [t, n, i] = await Promise.all([
      getJson<{ domains: TreeDomain[] }>('/api/tree'),
      getJson<NextDoc>('/api/next'),
      getJson<InterestDoc>('/api/interest'),
    ]);
    tree = t.domains;
    nextDoc = n;
    interests = i;
    renderTree();
    renderChanged();
    void refreshLearnerPeek();
    if (Object.keys(i.interest).length === 0) {
      firstRun = true;
      history.replaceState(null, '', '#interests');
    }
    route();
    addEventListener('hashchange', route);
  } catch (err) {
    fail(err);
  }
}

void start();

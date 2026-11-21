// [origin ref=llm-dsl-gu1y.5 req=REQ-OPERATOR-EDU-005,REQ-OPERATOR-EDU-007,REQ-OPERATOR-EDU-010 c4=learn_app/learn_spa]
//   [intent]Renders wave strip, topic tree, what-changed note, learner.json peek and the selected lesson from the JSON API, polling /api/now every 2s.[/intent]
//   [inv]The SPA only talks to the server's JSON API; Markdown HTML is escaped, never injected raw.[/inv]
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
    </article>`;
  wireDiagrams();
  renderTree();
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

function route(): void {
  const m = /^#lesson\/(.+)$/.exec(location.hash);
  if (m) void showLesson(decodeURIComponent(m[1]), 'You opened this lesson from the tree.').catch(fail);
  else if (nextDoc?.lesson) void showLesson(nextDoc.lesson.id, nextDoc.reason).catch(fail);
  else $('app').innerHTML = `<div class="why">${esc(nextDoc?.reason ?? 'No lesson available.')}</div>`;
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
  try {
    [tree, nextDoc] = await Promise.all([getJson<{ domains: TreeDomain[] }>('/api/tree').then((t) => t.domains), getJson<NextDoc>('/api/next')]);
    renderTree();
    renderChanged();
    void refreshLearnerPeek();
    route();
    addEventListener('hashchange', route);
  } catch (err) {
    fail(err);
  }
}

void start();

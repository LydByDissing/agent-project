// [origin ref=llm-dsl-gu1y.16 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Proves the Host/Origin/Content-Type guard: foreign pages cannot read or drive the server, and a rejected write never reaches claude or the learner file.[/intent]
// [/origin]
import { cpSync, existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import { loadLibrary } from '../src/library/load.js';
import { createApp } from '../src/server/app.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const FAKE = join(HERE, 'fixtures', 'fake-claude.mjs');
const PORT = 5151;
const tmp = (): string => mkdtempSync(join(tmpdir(), 'learn-guard-'));

function fixture() {
  const project = tmp();
  const home = tmp();
  cpSync(join(REPO, 'learn'), join(project, 'learn'), { recursive: true, preserveTimestamps: true });
  writeFileSync(join(project, 'index.html'), '<p>spa</p>');
  const log = join(tmp(), 'claude.log');
  process.env.FAKE_CLAUDE_LOG = log;
  const app = createApp({ port: PORT, project, distDir: project, home, claude: () => ({ bin: FAKE, timeoutMs: 10_000 }) });
  const lesson = loadLibrary(project).lessons[0];
  const calls = (): number => (existsSync(log) ? readFileSync(log, 'utf8').split('\n').filter(Boolean).length : 0);
  const req = (path: string, init: RequestInit & { host?: string } = {}) => {
    const { host = `127.0.0.1:${PORT}`, headers, ...rest } = init;
    return app.request(path, { ...rest, headers: { host, ...(headers as Record<string, string>) } });
  };
  return { app, req, lesson, calls, home, learnerFile: join(home, 'learner.json') };
}

afterEach(() => {
  delete process.env.FAKE_CLAUDE_LOG;
});

const JSON_H = { 'Content-Type': 'application/json' };

describe('Host guard', () => {
  it.each(['evil.example', 'evil.example:5151', '127.0.0.1', '127.0.0.1:9999', 'localhost', '127.0.0.1.evil.example:5151', '[::1]:5151'])('403 forbidden_host for Host %s on api and static routes', async (host) => {
    const f = fixture();
    for (const path of ['/api/health', '/api/learner', '/', '/api/nope']) {
      const res = await f.req(path, { host });
      expect(res.status, `${host} ${path}`).toBe(403);
      expect(((await res.json()) as { error: string }).error).toBe('forbidden_host');
    }
  });

  it.each(['127.0.0.1:5151', 'localhost:5151', 'LOCALHOST:5151'])('allows Host %s', async (host) => {
    const f = fixture();
    expect((await f.req('/api/health', { host })).status).toBe(200);
    expect((await f.req('/', { host })).status).toBe(200);
  });
});

describe('Origin guard', () => {
  it.each(['http://evil.example', 'http://127.0.0.1:9999', 'https://127.0.0.1:5151', 'null', 'http://localhost'])('403 forbidden_origin for Origin %s', async (origin) => {
    const f = fixture();
    const res = await f.req('/api/health', { headers: { Origin: origin } });
    expect(res.status).toBe(403);
    expect(((await res.json()) as { error: string }).error).toBe('forbidden_origin');
  });

  it.each(['http://127.0.0.1:5151', 'http://localhost:5151'])('allows same-origin %s', async (origin) => {
    const f = fixture();
    expect((await f.req('/api/health', { headers: { Origin: origin } })).status).toBe(200);
    const put = await f.req('/api/interest', { method: 'PUT', headers: { Origin: origin, ...JSON_H }, body: JSON.stringify({ key: f.lesson.domain, value: 'deep' }) });
    expect(put.status).toBe(200);
  });

  it('a foreign Origin on a write changes nothing and spawns no claude', async () => {
    const f = fixture();
    const q = await f.req(`/api/quiz/${f.lesson.id}`, { method: 'POST', headers: { Origin: 'http://evil.example', ...JSON_H } });
    const p = await f.req('/api/interest', { method: 'PUT', headers: { Origin: 'http://evil.example', ...JSON_H }, body: JSON.stringify({ key: f.lesson.domain, value: 'skip' }) });
    expect([q.status, p.status]).toEqual([403, 403]);
    expect(f.calls()).toBe(0);
    expect(existsSync(f.learnerFile)).toBe(false);
  });
});

describe('Content-Type guard', () => {
  it('415 on text/plain POST /api/quiz and spawns no claude', async () => {
    const f = fixture();
    const res = await f.req(`/api/quiz/${f.lesson.id}`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: '{}' });
    expect(res.status).toBe(415);
    expect(((await res.json()) as { error: string }).error).toBe('unsupported_media_type');
    expect(f.calls()).toBe(0);
  });

  it('415 on POST /api/quiz without a content type, none still spawns nothing', async () => {
    const f = fixture();
    expect((await f.req(`/api/quiz/${f.lesson.id}`, { method: 'POST' })).status).toBe(415);
    expect(f.calls()).toBe(0);
  });

  it('415 on text/plain PUT /api/interest and learner.json is not written', async () => {
    const f = fixture();
    const res = await f.req('/api/interest', { method: 'PUT', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ key: f.lesson.domain, value: 'deep' }) });
    expect(res.status).toBe(415);
    expect(existsSync(f.learnerFile)).toBe(false);
  });

  it('415 on text/plain POST /api/answer and on DELETE', async () => {
    const f = fixture();
    expect((await f.req('/api/answer', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: '{}' })).status).toBe(415);
    expect((await f.req('/api/interest', { method: 'DELETE' })).status).toBe(415);
  });

  it('accepts application/json with a charset, and a same-origin quiz request really runs claude', async () => {
    const f = fixture();
    const res = await f.req(`/api/quiz/${f.lesson.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8', Origin: `http://127.0.0.1:${PORT}` } });
    expect(res.status).toBe(200);
    expect(f.calls()).toBe(1);
  });

  it('GET needs no content type', async () => {
    const f = fixture();
    expect((await f.req('/api/health')).status).toBe(200);
  });
});

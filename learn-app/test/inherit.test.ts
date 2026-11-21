// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.16 req=REQ-OPERATOR-EDU-006 c4=learn_app/learn_server]
//   [intent]Proves PUT /api/interest value inherit deletes a topic's own setting, is rejected on domain keys, and is atomic with the rest of a batch.[/intent]
// [/origin]
import { cpSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { tmp as tmpDir } from './helpers/tmp.js';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { loadLibrary } from '../src/library/load.js';
import { makeApp } from './helpers/app.js';

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const tmp = (): string => tmpDir('learn-inherit-');

function fixture(interest: Record<string, string>) {
  const project = tmp();
  const home = tmp();
  cpSync(join(REPO, 'learn'), join(project, 'learn'), { recursive: true, preserveTimestamps: true });
  writeFileSync(join(home, 'learner.json'), JSON.stringify({ schema: 1, interest, mastery: {}, history: [] }));
  const app = makeApp({ project, distDir: project, home });
  const lib = loadLibrary(project);
  const d = lib.domains.find((x) => x.topics.length > 0)!;
  const topic = `${d.id}/${d.topics[0].slug}`;
  const put = (body: unknown) => app.request('/api/interest', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const onDisk = (): Record<string, string> => JSON.parse(readFileSync(join(home, 'learner.json'), 'utf8')).interest;
  return { d, topic, put, onDisk };
}

describe('interest inherit', () => {
  it('removes the topic key and keeps the domain key and other topics', async () => {
    const f = fixture({});
    const other = f.d.topics[1] ? `${f.d.id}/${f.d.topics[1].slug}` : undefined;
    await f.put({ [f.d.id]: 'deep', [f.topic]: 'skip', ...(other ? { [other]: 'basics' } : {}) });
    const res = await f.put({ key: f.topic, value: 'inherit' });
    expect(res.status).toBe(200);
    const body = (await res.json()) as { interest: Record<string, string> };
    expect(body.interest).toEqual(f.onDisk());
    expect(f.onDisk()[f.d.id]).toBe('deep');
    expect(f.topic in f.onDisk()).toBe(false);
    if (other) expect(f.onDisk()[other]).toBe('basics');
  });

  it('inherit on a topic with no own setting is a no-op success', async () => {
    const f = fixture({});
    expect((await f.put({ key: f.topic, value: 'inherit' })).status).toBe(200);
    expect(f.onDisk()).toEqual({});
  });

  it('inherit on a domain key is 400 bad_value and writes nothing', async () => {
    const f = fixture({});
    await f.put({ [f.d.id]: 'deep' });
    const res = await f.put({ key: f.d.id, value: 'inherit' });
    expect(res.status).toBe(400);
    expect(((await res.json()) as { error: string }).error).toBe('bad_value');
    expect(f.onDisk()).toEqual({ [f.d.id]: 'deep' });
  });

  it('a batch with a valid topic inherit and a domain inherit is rejected whole', async () => {
    const f = fixture({});
    await f.put({ [f.d.id]: 'deep', [f.topic]: 'skip' });
    const res = await f.put({ [f.topic]: 'inherit', [f.d.id]: 'inherit' });
    expect(res.status).toBe(400);
    expect(f.onDisk()).toEqual({ [f.d.id]: 'deep', [f.topic]: 'skip' });
  });

  it('inherit is not accepted for an unknown topic key', async () => {
    const f = fixture({});
    expect((await f.put({ key: `${f.d.id}/no-such-topic`, value: 'inherit' })).status).toBe(400);
  });
});

describe('settings UI inherit control', () => {
  it('the SPA bundle renders an inherit button on topic rows and sends value inherit', () => {
    const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'assets');
    const js = readdirSync(dir).filter((f) => f.endsWith('.js')).map((f) => readFileSync(join(dir, f), 'utf8')).join('\n');
    expect(js).toMatch(/\["deep","basics","skip","inherit"\]/);
    expect(js).toMatch(/inherit"\?\w+===void 0:/);
  });
});

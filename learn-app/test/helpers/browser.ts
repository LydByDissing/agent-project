// [origin ref=llm-dsl-gu1y.17 req=REQ-OPERATOR-EDU-002,REQ-OPERATOR-EDU-003,REQ-OPERATOR-EDU-010,REQ-OPERATOR-EDU-011 c4=learn_app/learn_spa]
//   [intent]Shared headless snap Chromium driver over the DevTools protocol (Node WebSocket) whose throwaway profile dirs are always removed, with a visible-skip flag when Chromium is unavailable.[/intent]
// [/origin]
import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { afterAll } from 'vitest';
import { freePort, sleep } from './server.js';
import { tmp } from './tmp.js';

export const CHROMIUM = '/snap/bin/chromium';
// Snap confinement: chromium can only write below this directory.
export const SNAP_COMMON = join(homedir(), 'snap', 'chromium', 'common');
export const canRunChromium = existsSync(CHROMIUM) && existsSync(SNAP_COMMON);

export interface Page {
  evaluate: <T>(expression: string) => Promise<T>;
  waitFor: (expression: string, label: string, ms?: number) => Promise<void>;
  close: () => Promise<void>;
}

type Reply = { result?: { result?: { value?: unknown }; exceptionDetails?: { text: string } } };
const open = new Set<Page>();

afterAll(async () => {
  await closeAllPages();
});

export async function closeAllPages(): Promise<void> {
  await Promise.all([...open].map((p) => p.close()));
}

async function removeProfile(dir: string): Promise<void> {
  for (let i = 0; i < 20; i++) {
    try {
      rmSync(dir, { recursive: true, force: true });
      if (!existsSync(dir)) return;
    } catch {
      // snap chromium may still be flushing its profile; retry after it has exited
    }
    await sleep(250);
  }
  throw new Error(`could not remove chromium profile ${dir}`);
}

/** Launches headless chromium on a throwaway profile, opens `url` in a tab and returns an evaluate/waitFor driver. */
export async function launchPage(url: string, windowSize = '1200,900'): Promise<Page> {
  const port = await freePort();
  const profile = tmp('learn-chromium-ud-', SNAP_COMMON);
  const proc: ChildProcess = spawn(
    CHROMIUM,
    ['--headless', '--no-sandbox', '--disable-gpu', `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, '--remote-allow-origins=*', `--window-size=${windowSize}`, 'about:blank'],
    { stdio: 'ignore' },
  );
  const exited = new Promise<void>((res) => proc.once('exit', () => res()));
  let ws: WebSocket | undefined;
  let closed = false;
  const page: Page = {
    evaluate: async () => {
      throw new Error('page not ready');
    },
    waitFor: async () => {
      throw new Error('page not ready');
    },
    close: async () => {
      if (closed) return;
      closed = true;
      open.delete(page);
      try {
        ws?.close();
        const v = (await (await fetch(`http://127.0.0.1:${port}/json/version`)).json()) as { webSocketDebuggerUrl: string };
        const bws = new WebSocket(v.webSocketDebuggerUrl);
        await new Promise<void>((res) => {
          bws.onopen = () => {
            bws.send(JSON.stringify({ id: 1, method: 'Browser.close' }));
            res();
          };
          bws.onerror = () => res();
        });
      } catch {
        // browser already gone
      }
      await Promise.race([exited, sleep(5000)]);
      if (proc.exitCode === null && proc.signalCode === null && proc.pid) {
        try {
          process.kill(proc.pid, 'SIGKILL');
        } catch {
          // already exited
        }
        await Promise.race([exited, sleep(2000)]);
      }
      await removeProfile(profile);
    },
  };
  open.add(page);
  try {
    const end = Date.now() + 30_000;
    for (;;) {
      try {
        await fetch(`http://127.0.0.1:${port}/json/version`);
        break;
      } catch {
        if (Date.now() > end) throw new Error('chromium DevTools endpoint never came up');
        await sleep(200);
      }
    }
    const target = (await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' })).json()) as { webSocketDebuggerUrl: string };
    const sock = new WebSocket(target.webSocketDebuggerUrl);
    ws = sock;
    await new Promise<void>((res, rej) => {
      sock.onopen = () => res();
      sock.onerror = () => rej(new Error('DevTools websocket failed'));
    });
    let seq = 0;
    const pending = new Map<number, (m: Reply) => void>();
    sock.onmessage = (ev) => {
      const m = JSON.parse(String(ev.data)) as { id?: number };
      if (m.id !== undefined) pending.get(m.id)?.(m as Reply);
    };
    page.evaluate = async <T,>(expression: string): Promise<T> => {
      const id = ++seq;
      const reply = await new Promise<Reply>((res) => {
        pending.set(id, res);
        sock.send(JSON.stringify({ id, method: 'Runtime.evaluate', params: { expression, awaitPromise: true, returnByValue: true } }));
      });
      pending.delete(id);
      if (reply.result?.exceptionDetails) throw new Error(`page eval failed: ${reply.result.exceptionDetails.text}`);
      return reply.result?.result?.value as T;
    };
    page.waitFor = async (expression: string, label: string, ms = 20_000): Promise<void> => {
      const end = Date.now() + ms;
      while (!(await page.evaluate<boolean>(`Boolean(${expression})`))) {
        if (Date.now() > end) throw new Error(`timed out waiting for ${label} in the page`);
        await sleep(100);
      }
    };
    return page;
  } catch (e) {
    await page.close();
    throw e;
  }
}

// [origin ref=llm-dsl-gu1y.17 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_spa]
//   [intent]Test helper that hands out private temp directories and removes every one of them when the importing test file finishes, so no test leaves files behind.[/intent]
// [/origin]
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll } from 'vitest';

const created: string[] = [];

/** Creates a fresh directory under the OS temp dir (or `parent`); removed after the importing file's tests. */
export function tmp(prefix = 'learn-test-', parent = tmpdir()): string {
  const dir = mkdtempSync(join(parent, prefix));
  created.push(dir);
  return dir;
}

export function cleanupTmp(): void {
  for (const dir of created.splice(0)) rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}

afterAll(cleanupTmp);

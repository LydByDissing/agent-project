// [origin ref=llm-dsl-gu1y.1 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_server]
//   [intent]Resolves request-supplied paths under a fixed root and rejects any that escape it.[/intent]
//   [inv]resolveUnder never returns a path outside its root.[/inv]
// [/origin]
import { resolve, sep } from 'node:path';

export class PathEscapeError extends Error {
  constructor(readonly requested: string) {
    super(`path escapes root: ${requested}`);
    this.name = 'PathEscapeError';
  }
}

export function resolveUnder(root: string, requested: string): string {
  if (requested.includes('\0')) throw new PathEscapeError(requested);
  const base = resolve(root);
  const target = resolve(base, requested.replace(/^\/+/, ''));
  if (target !== base && !target.startsWith(base + sep)) throw new PathEscapeError(requested);
  return target;
}

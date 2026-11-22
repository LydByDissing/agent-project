// [origin ref=llm-dsl-gu1y.16 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_spa]
//   [intent]Proves safeHref lets only absolute http(s), fragments and single-slash paths through.[/intent]
// [/origin]
import { describe, expect, it } from 'vitest';
import { safeHref } from '../src/spa/href.js';

describe('safeHref', () => {
  it.each(['https://example.com/a?b=1', 'http://example.com', 'HTTPS://example.com', '#frag', '/api/asset/x.svg', '/'])('keeps %s', (h) => {
    expect(safeHref(h)).toBe(h);
  });
  it.each(['//evil.example/x', '//evil.example', '/\\evil.example', 'javascript:alert(1)', 'data:text/html,x', 'mailto:a@b.c', 'ftp://x', 'relative/path', '', 'https:evil'])('rejects %s', (h) => {
    expect(safeHref(h)).toBe('#');
  });
});

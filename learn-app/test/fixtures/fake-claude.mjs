#!/usr/bin/env node
// [origin ref=llm-dsl-gu1y.17,llm-dsl-gu1y.7 req=REQ-OPERATOR-EDU-008 c4=learn_app/question_generator]
//   [intent]Fake claude CLI for tests: reads the prompt from stdin, writes a JSON envelope per FAKE_CLAUDE_MODE and records the prompt and argv.[/intent]
// [/origin]
import { appendFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs';

let prompt = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (d) => (prompt += d));
process.stdin.on('end', () => {
  // FAKE_CLAUDE_MODE_FILE (optional) is re-read on every call, so a test can flip the mode while a server keeps running.
  const modeFile = process.env.FAKE_CLAUDE_MODE_FILE;
  const mode = modeFile && existsSync(modeFile) ? readFileSync(modeFile, 'utf8').trim() : (process.env.FAKE_CLAUDE_MODE ?? 'valid');
  if (process.env.FAKE_CLAUDE_PROMPT_FILE) writeFileSync(process.env.FAKE_CLAUDE_PROMPT_FILE, prompt);
  if (process.env.FAKE_CLAUDE_LOG) appendFileSync(process.env.FAKE_CLAUDE_LOG, JSON.stringify(process.argv.slice(2)) + '\n');
  const q = (i, over = {}) => ({
    q: `Question ${i + 1} about the lesson?`,
    options: [0, 1, 2].map((k) => ({ text: `Option ${k}`, explanation: `Because ${k}` })),
    correct: 1,
    source: 's1',
    ...over,
  });
  let qs = [q(0), q(1), q(2)];
  if (mode === 'wrong-count') qs = [q(0), q(1)];
  if (mode === 'two-correct') qs[1] = q(1, { correct: [0, 1] });
  if (mode === 'unknown-source') qs[2] = q(2, { source: 's99' });
  if (mode === 'exit') {
    process.stderr.write('boom: not logged in\n');
    process.exit(3);
  }
  if (mode === 'sleep') {
    setTimeout(() => {}, 60_000);
    return;
  }
  if (mode === 'garbage') return void process.stdout.write('not json at all');
  const json = JSON.stringify({ questions: qs });
  const result = mode === 'fenced' ? 'Here you go:\n```json\n' + json + '\n```\n' : json;
  process.stdout.write(JSON.stringify({ type: 'result', subtype: 'success', is_error: false, result }));
});

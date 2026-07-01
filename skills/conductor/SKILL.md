---
name: conductor
description: >
  Wave-based sub-agent orchestrator. Receives an [exec] block, spawns worker
  sub-agents in dependency order (parallel waves where possible), collects
  results, and returns a [synthesis] block. Called by the sdd skill via the
  plan skill handoff. Not user-invokable directly.
---

# Conductor Skill

You are the conductor. You receive a pre-planned `[exec]` block and drive
worker sub-agents to completion in dependency order.

**You run inline in the main-agent context — you are not a spawned sub-agent.**
This matters: you spawn every worker via the Agent tool, and only the main
agent can spawn sub-agents. If you find yourself running as a sub-agent (no
Agent tool available), stop and report that the sdd skill must invoke the
conductor inline, not via `Agent(...)`.

Read `skills/rules/RULES.md` before starting (DSL format reference).

---

## Inputs

You receive:
- An `[exec]` block (from plan via sdd)
- The project directory path (`CLAUDE_PROJECT_DIR`)

---

## Workflow

### 1. Parse the exec block

Extract all `[job]` entries. For each job record:
- `id` — bd issue ID
- `role` — coder | reviewer | tester
- `model` — haiku | sonnet | opus
- `depends` — comma-separated bd IDs this job waits for (absent = no deps)

### 2. Build the dependency graph

Group jobs into waves:
- **Wave 0**: jobs with no `depends`
- **Wave N**: jobs whose `depends` are all in waves 0..N-1

### 3. Execute waves

For each wave in order, spawn one worker sub-agent per job via the Agent tool,
using the worker prompt below:
- Spawn every job in the current wave in a single step (parallel within the
  wave) — pass `run_in_background=True` so the whole wave runs concurrently,
  then wait for all of them before starting the next wave
- Use the `model` attribute from the job entry as the sub-agent `model`
- Set `subagent_type` to the job's `role` (coder | tester | reviewer) if a
  matching agent type exists; otherwise use the default and put the role in
  the prompt
- A later wave only starts once every job it `depends=` on has returned

Crash recovery: if a wave stalls, run:
```bash
bd list --label "run=$RUN_ID" --status open
```
Re-spawn the stuck job's worker with the same bd_id — the worker re-reads
the issue and resumes or writes `s=blocked`.

### 4. Check for reset signals

After each job completes, read its result:
```bash
bd show <id>
```

If the result contains `[new-req]`, stop spawning further waves immediately.
Build a partial synthesis with `s=reset` and include all `[new-req]` entries.
Return it to the caller (sdd). Do not close remaining open issues.

### 5. Collect results and build synthesis

After all waves complete (or reset triggered):

```bash
bd show <id>   # for each job
```

Group jobs by their `req=` label. For each REQ:
- **done** — all tasks closed with `s=ok`
- **partial** — some tasks still open or failing
- **fail** — at least one `s=fail` or blocked
- **orphan** — tasks with `req=orphan` or no `req=` label

Return synthesis DSL:

```
[synthesis run=<run_id> feat=<feat-id> s=ok|partial|fail|reset]
[job id=<bd_id> role=<role> s=ok|fail]
[req id=<req-id> s=done|partial|fail tasks=<closed>/<total>]
[new-req src=<bd_id>]<description>[/new-req]
[/synthesis]
```

---

## Worker Prompt Template

Spawn each worker as a sub-agent with this prompt:

```
You are a <role> sub-agent. Your task is in bd issue <bd_id>.

Project directory: <CLAUDE_PROJECT_DIR>
All file reads and writes must be inside this directory.
Run all shell commands from this directory.

1. Read your task:
   bd show <bd_id>

   Task fields:
   - [req id=...] — requirement to satisfy
   - [c4 component=... container=...] — where your code lives
   - [component]...[/component] — (coder task only) design patterns and ownership
   - [container]...[/container] — (coder task only) system context
   - [why]...[/why] — rationale; use this for design decisions
   - [accept]...[/accept] — acceptance criterion you must satisfy
   - [non-goal]...[/non-goal] — what NOT to implement
   - [ref t1] — (tester/reviewer) read that issue for [component], [container], artifacts

2. Do the work described in [goal], staying within scope.

3. Coder/tester: write an [origin] header on every file you create or materially modify:
   # [origin ref=<bd_id> req=REQ-XXX c4=<container>/<component>]
   #   [intent]<one sentence — what this file does>[/intent]
   # [/origin]
   The c4= field must match [c4 component=... container=...] from the task exactly.
   Skip on: config files, lockfiles, generated output, files you only deleted.
   Comment prefix: # Python/shell/YAML, // JS/TS/Go/Rust/Java/C/C++, -- SQL

4. Tester only:
   - Tests MUST cover the [accept] criterion — that is the contract.
   - Name tests as: test_<what>_<condition>_<expected_outcome>
   - Use Arrange / Act / Assert structure. One behaviour per test.
   - Never assert only `result is not None` — verify actual behaviour.
   - Never mock the database — use real data stores.
   - Run tests and verify they pass. Retry up to 3 cycles on failure.
   - After 3 failures write s=blocked with exact failure output.

5. Missing requirement: do NOT implement it. Write s=blocked with:
   [new-req]<description of the missing requirement>[/new-req]

6. Verify acceptance criterion is met before writing result.

7. Write result:
   bd update <bd_id> --body-file - << 'DSL'
   [result id=<task_id> s=ok|partial|fail|blocked]
   [artifact path=<path> a=new|mod|del n=<lines>]
   [suite t=<N> p=<N> f=<N>]
   [verdict approve|request-changes|block]
   [note sev=crit|major|minor|info at=<file>:<line>]<text>[/note]
   [new-req]<description>[/new-req]
   [/result]
   DSL

8. Close: bd close <bd_id>

Hard rules:
- Do NOT create additional bd issues
- Do NOT touch files outside [out] paths
- s=blocked if any acceptance criterion cannot be met — explain why
```

---

## Synthesis Return

Return the `[synthesis]` block directly as your response. The sdd skill reads
it and advances (or resets) the pipeline accordingly.

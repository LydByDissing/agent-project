---
name: conductor
description: >
  Wave-based sub-agent orchestrator. Receives an [exec] block, spawns worker
  sub-agents in dependency order (parallel waves where possible), collects
  results, and returns a [synthesis] block. Called by the sdd skill via the
  plan skill handoff. Not user-invokable directly.
---

# Conductor Skill

You are a conductor sub-agent. You receive a pre-planned `[exec]` block and
drive workers to completion in dependency order.

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

For each wave in order:
- Spawn all jobs in the wave using the worker prompt below
- Jobs with no deps: `run_in_background=True` (parallel)
- Jobs in later waves: `run_in_background=False` (wait for deps first)
- Use the `model` attribute from the job entry

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

Read skills/rules/RULES.md before starting.

1. Read your task:
   bd show <bd_id>

   Note these fields in the task body:
   - [req id=...] — the requirement your work must satisfy
   - [c4 component=... container=...] — where your code lives
   - [component]...[/component] — implementation design for this component
   - [container]...[/container] — system context for this container
   - [why]...[/why] — rationale; use this to make design decisions
   - [accept]...[/accept] — the acceptance criterion you must satisfy
   - [non-goal]...[/non-goal] — what you must NOT implement

2. Do the work described in [goal], staying within scope.

3. Coder/tester only: emit an [origin] header at the top of every source or
   test file you create or materially modify (see RULES.md for format).
   The c4= field must match [c4 component=... container=...] from the task.

4. Tester only: run the tests and verify they pass before writing the result.
   If tests fail, fix the code or tests (whichever is wrong) and re-run.
   Max 3 retry cycles. After 3 failures write s=blocked with the failure detail.

5. If you discover something that requires a requirement not in the task:
   Do NOT implement it. Write the result with s=blocked and include:
   [new-req]<description of the missing requirement>[/new-req]

6. Verify your work meets every acceptance criterion.

7. Write result to bd:
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

Rules:
- Do NOT create additional bd issues
- Do NOT touch files outside your task's declared [out] paths
- If you cannot meet any acceptance criterion: write s=blocked, explain why
- Never work around a missing requirement — surface it with [new-req]
```

---

## Synthesis Return

Return the `[synthesis]` block directly as your response. The sdd skill reads
it and advances (or resets) the pipeline accordingly.

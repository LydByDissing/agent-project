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

**Then collapse any wave whose jobs share a compilation/verification unit.**
Two jobs writing into the same Maven/Gradle module, Go module, Rust crate,
.NET project, or Python package with a shared test run are NOT parallel — each
one's build compiles the other's half-written files. Run them one at a time even
though the exec block places them in the same wave, and even though their
`[out]` paths are disjoint. See the plan skill's compilation-unit rule for what
this costs when ignored.

A wave may only run in parallel when each job can be **verified alone**.

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

### 3b. Verify each job independently — do not trust its self-report

`bd show <id>` returns the worker's **own account of its work**. That is evidence
of intent, not of outcome. In a real run of this pipeline, self-reports included
a `BUILD SUCCESS` obtained by excluding the failing test, a task claiming its
acceptance criterion was met with **zero tests written**, and two workers
asserting directly contradictory things about the same test.

After each job closes, before starting anything that depends on it:

1. **Re-run the project's full verification yourself** (`mvn verify`,
   `pytest`, `cargo test`, …) and compare the real counts against the reported
   ones. This alone catches a green-by-exclusion build.
2. **Check scope independently.** Confirm the job touched only its `[out]` paths,
   using a diff, `git status`, or file modification times — not the worker's
   claim. If the tree is untracked, mtimes are enough.
3. **Attack the guarantee.** For any job whose acceptance criterion rests on an
   invariant — a boundary, an append-only rule, a determinism or equivalence
   property — deliberately introduce the failure it claims to prevent, confirm
   the test fails, then revert. A two-line sabotage and one test run.

   This is the highest-value check available and it is cheap. In one run it was
   applied five times: four guarantees held, and the fifth exposed a real
   data-loss defect that every reported test had missed.

   Watch specifically for tests that **cannot fail**: a loop asserting a property
   over a collection that may be empty, a boundary scan that matches nothing, or
   a constant that happens to satisfy the assertion. A suite can be entirely
   green and verify nothing.

If verification contradicts the report, reopen the issue, record what you found,
and treat the job as unfinished regardless of what it claimed.

### 4. Check for reset signals

After each job completes, read its result:
```bash
bd show <id>
```

If the result contains `[new-req]`, act on its **severity** (see RULES.md):

- `sev=blocks-milestone`, or no severity given — stop spawning further waves
  immediately. Build a partial synthesis with `s=reset`, include all `[new-req]`
  entries, and return it to `sdd`. Do not close remaining open issues.
- `sev=blocks-slice` — leave that issue open, record the requirement, and
  continue the remaining waves. Report it in the synthesis but do not reset.
- `sev=noted` — record it and continue. Surface it in the synthesis so the
  requirement reaches the docs, but neither stop nor reset.

Resetting the whole pipeline for every discovered requirement is paralysing: a
single milestone can legitimately surface several. Recording the gap, amending
the docs and filing a tracked issue keeps the specification honest without
discarding work that is already correct.

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

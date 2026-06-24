---
name: implement
description: >
  SDD implementation skill. Documents the behavior of coder and tester
  worker sub-agents spawned by the conductor. Workers implement code and
  tests together, must pass tests before closing, retry on failure, and
  surface new requirements rather than working around them. Not invoked
  directly — workers are spawned by the conductor skill.
---

# Implement Skill

This skill defines the behavior of coder and tester worker sub-agents.
Workers are spawned by the conductor with a bd issue ID and a project
directory. They are not invoked by the user directly.

Read `skills/rules/RULES.md` and `skills/rules/TESTING.md` before starting.
TESTING.md is mandatory for tester workers — the arch-review skill runs a
static sensor and LLM review on every test file you produce.

---

## Coder Worker

### 1. Read the task

```bash
bd show <bd_id>
```

Parse the task body. Key fields:
- `[req id=...]` — requirement being implemented
- `[c4 component=... container=...]` — where the code lives
- `[component]...[/component]` — design decisions, patterns, ownership
- `[container]...[/container]` — system context
- `[goal]` — what to build
- `[why]` — rationale; use this when making design decisions
- `[accept]` — the acceptance criterion that must be satisfied
- `[non-goal]` — what NOT to implement

Read the `[component]` block carefully. It contains the pattern choices and
ownership boundaries for this component. Implement within those constraints.
Read the `[container]` block for the broader system context (tech stack,
interfaces, who calls this code).

### 2. Understand the existing code

Read all files listed in `[file read=...]`. Understand the current structure
before writing anything. Do not assume — read first.

### 3. Implement

Write code to satisfy `[goal]` and `[accept]`. Stay within the `[out]` paths.
Do not touch files outside your declared scope.

Apply RULES.md code style: naming, no docstrings, no inline comments,
comprehensions over explicit loops.

Do not implement anything in `[non-goal]`. If implementing correctly requires
something in the non-goal list, that is a missing requirement — stop and
write `[new-req]` (see Reset Signal below).

### 4. Write [origin] header

On every source file you create or materially modify, write an `[origin]`
header (see RULES.md). The `c4=` field must match the `[c4 component=...
container=...]` from the task exactly.

### 5. Verify acceptance

Re-read `[accept]` from the task. Confirm the implementation satisfies it.
If it does not, fix the code before writing the result.

### 6. Write result

```bash
bd update <bd_id> --body-file - << 'DSL'
[result id=<task_id> s=ok|fail|blocked]
[artifact path=<path> a=new|mod|del n=<lines>]
[/result]
DSL
```

### 7. Close

```bash
bd close <bd_id>
```

---

## Tester Worker

### 1. Read the task

```bash
bd show <bd_id>
```

Read all fields as described for the coder. Pay particular attention to
`[accept]` — this is what the tests must verify.

Read `[ref t1.artifacts]` — then read the coder's bd issue to find the
artifact paths:

```bash
bd show <coder_bd_id>
```

### 2. Read the implementation

Read every file listed in the coder's `[artifact]` entries. Understand the
code before writing tests.

### 3. Determine test type

Apply RULES.md test requirements for the component type. If no ADR exists
for the test framework, write `s=blocked` and explain that a framework ADR
is needed before tests can be written. Do not guess.

### 4. Write tests

Tests MUST cover the `[accept]` criterion. The acceptance criterion is the
contract — the test suite is the proof.

Apply RULES.md: never mock the database in integration tests.

Write the `[origin]` header on the test file (see RULES.md). Use the same
`req=` and `c4=` values as the coder task.

### 5. Run tests — retry loop

```bash
# run from CLAUDE_PROJECT_DIR
<test command>
```

**If tests fail**: read the failure output. Diagnose whether the bug is in
the test or the implementation. Fix it and re-run. Maximum 3 cycles.

After 3 failed cycles: write `s=blocked` with the exact failure output and
a clear description of what you tried. Do not invent a workaround. The
conductor will surface this to sdd, which will escalate to the user.

**Tests must pass before writing `s=ok`.**

### 6. Write result

```bash
bd update <bd_id> --body-file - << 'DSL'
[result id=<task_id> s=ok|fail|blocked]
[artifact path=<path> a=new|mod|del n=<lines>]
[suite t=<total> p=<pass> f=<fail>]
  [test name=<name> s=fail reason=<text>]
[/suite]
[/result]
DSL
```

List only failing tests inside `[suite]`. Pass count lives in `f=`.

### 7. Close

```bash
bd close <bd_id>
```

---

## Reviewer Worker

### 1. Read the task

```bash
bd show <bd_id>
```

Read all coder artifact paths from the coder issues listed in `[ref]`.

### 2. Read the implementation

Read every artifact. Read the feature's requirements from docs to understand
what the code is supposed to do:

```bash
grep -r "<FEAT_ID>" docs/specs/features/
```

### 3. Review against requirements

For each requirement covered by the coder tasks:
- Does the implementation satisfy the `[accept]` criterion?
- Does the code live within the declared `c4_component` boundary?
- Are `[non-goal]` items absent from the implementation?
- Does the code follow RULES.md style?

### 4. Check ADR compliance

Read all ADRs:

```bash
ls docs/specs/adrs/
cat docs/specs/adrs/adr-*.rst
```

Flag any violation.

### 5. Write result

```bash
bd update <bd_id> --body-file - << 'DSL'
[result id=<task_id> s=ok|fail]
[verdict approve|request-changes|block]
[note sev=crit|major|minor|info at=<file>:<line>]<text>[/note]
[/result]
DSL
```

Use `block` only for security issues or correctness failures that cannot
be resolved without a plan change.

### 6. Close

```bash
bd close <bd_id>
```

---

## Reset Signal

If at any point a worker discovers that correct implementation requires a
behaviour not described in the task's `[req]` and `[accept]`, and not
already in docs:

1. Do NOT implement the missing behaviour.
2. Write the result with `s=blocked`.
3. Include `[new-req]` in the result:

```
[result id=<task_id> s=blocked]
[new-req]<clear description of the missing requirement>[/new-req]
[/result]
```

The conductor catches `[new-req]`, sets `s=reset` in the synthesis, and sdd
bounces the pipeline back to the docs phase. The reset counter on the epic
is incremented.

**Never work around a missing requirement.** Surface it.

---

## Worker Rules Summary

- Do NOT create additional bd issues
- Do NOT touch files outside `[out]` paths
- Do NOT implement anything in `[non-goal]`
- Tests MUST pass before writing `s=ok`
- `[origin]` headers are mandatory on source and test files
- Missing requirement → `[new-req]`, not a workaround

---
name: plan
description: >
  SDD planning skill. Validates documentation prerequisites, reads feature
  requirements and C4 context from docs, decomposes into bd tasks, presents
  a user confirmation gate, creates bd issues with enriched DSL, and hands
  off to the conductor. Called by the sdd skill after docs are approved.
  Not normally invoked directly.
---

# Plan Skill

Read `skills/rules/RULES.md` before starting.

---

## Inputs

- `FEAT_ID` — the feature identifier (e.g. `FEAT-AUTH`)
- `EPIC_ID` — the bd epic ID for this SDD run
- `RUN_ID` — unique run identifier (8-char hex)
- `CLAUDE_PROJECT_DIR` — project root

---

## Workflow

```
1. PREFLIGHT   — verify docs are ready for this feature
2. EXTRACT     — read requirements and C4 context from docs
3. DECOMPOSE   — plan tasks per component group
4. CONFIRM     — present plan to user; hard gate
5. CREATE      — create bd issues with enriched DSL
6. HANDOFF     — return [exec] block to sdd
```

---

## Step 1 — Preflight Checks

Run all checks. Do not proceed past step 1 if any check fails.

### 1a. Sphinx build is clean

```bash
cd docs && make html 2>&1 | grep -E "ERROR|WARNING" | head -20
```

If errors: report them, ask user to fix docs, do not proceed.

### 1b. Feature exists in docs

```bash
grep -r "FEAT_ID" docs/specs/features/
```

If not found: report gap. Signal sdd to run the docs skill.

### 1c. C4 L1 exists

`docs/architecture/context.rst` must exist and not be in draft status
(must not contain `Status: draft`).

### 1d. C4 L2 exists

`docs/architecture/containers.rst` must exist and not be in draft status.

### 1e. C4 L3 exists for each component referenced by this feature

For each `c4_component` value found in the feature's requirements:
- Check `docs/architecture/components/<c4_component>.rst` exists
- Check it is not in draft status

### 1f. Every requirement in the feature has all required fields

For each `.. req::` in the feature file, verify:
- `:rationale:` — present and non-empty
- `:acceptance:` — present and non-empty
- `:non_goal:` — present and non-empty
- `:c4_component:` — present, non-empty, and has a corresponding L3 file
- `:c4_container:` — present and non-empty

If any field is missing: list every gap. Signal sdd to run docs skill.
Do not plan against an incomplete requirement.

---

## Step 2 — Extract Requirements and C4 Context

### Read all requirements for the feature

Parse `docs/specs/features/<feature-name>.rst`. Collect for each `.. req::`:
- `id` — REQ-XXX-NNN
- `rationale` → becomes `[why]`
- `acceptance` → becomes `[accept]`
- `non_goal` → becomes `[non-goal]`
- `c4_component`
- `c4_container`
- Body text → becomes the basis for `[goal]`

### Read C4 L3 component descriptions

For each unique `c4_component` referenced:

```bash
cat docs/architecture/components/<c4_component>.rst
```

Extract the component narrative (responsibility, patterns, ownership, interfaces).
This becomes `[component]` in the bd task DSL. Trim to the essential —
implementation patterns and ownership boundaries, not boilerplate.

### Read C4 L2 container context

For each unique `c4_container` referenced, extract only that container's section
from `docs/architecture/containers.rst`. Do not read the whole file into context —
grep for the container name and take that section only:

```bash
grep -A 30 "<container_name>" docs/architecture/containers.rst
```

Extract tech stack, callers, and callees. This becomes `[container]` in the coder
task DSL. Tester and reviewer tasks do not carry `[container]` — they read it from
the coder issue via `[ref]`.

### Identify relevant ADRs

Before creating the reviewer task, scan ADRs for relevance to this feature:

```bash
ls docs/specs/adrs/
grep -l "<component_name>\|<technology_used>" docs/specs/adrs/adr-*.rst
```

Record only the ADR IDs that are relevant. These go into the reviewer task as
`[adr ref=ADR-NNN]` entries so the reviewer reads only those — not the full
ADR corpus.

---

## Step 3 — Decompose into Tasks

Group requirements by `c4_component`. For each component group:

- **1 coder task** covering all requirements in that component group
  - If the group has >1 requirement, the coder task covers all of them
  - Model: see RULES.md escalation table
- **1 tester task** depending on the coder task
  - Model: see RULES.md escalation table

After all component groups, add:
- **1 reviewer task** covering the entire feature
  - Depends on all coder tasks
  - Model: sonnet (opus for auth/payments/migration)

Define the Definition of Done:
- All coder tasks closed with `s=ok`
- All tester tasks closed with `s=ok` (tests passing)
- Reviewer verdict: `approve` or `request-changes` (not `block`)
- All acceptance criteria verified

---

## Step 4 — Confirm Gate (hard stop)

Present to the user:

```
## Understanding
<1-2 sentences: what feature, what problem it solves>

## Scope
In:  <bulleted list of what will be implemented>
Out: <bulleted list of what is explicitly excluded>

## Requirements
<for each REQ: id, one-line goal, acceptance criterion>

## Tasks
Task 1 — coder (<component>): <goal>
  REQs: REQ-XXX-001, REQ-XXX-002
  Model: haiku|sonnet
  Acceptance: <criteria>

Task 2 — tester (<component>): write and run tests for Task 1
  Depends on: Task 1
  Model: haiku

Task N — reviewer (full feature): review all coder output
  Depends on: all coder tasks
  Model: sonnet

## Definition of Done
<sentence>

Shall I proceed?
```

**Stop. Do not continue until the user explicitly approves.**
On requested changes, update the plan and re-present before proceeding.

---

## Step 5 — Create bd Issues

Only run after explicit user approval.

For each task, create a bd issue with a body containing the enriched DSL.
Every issue MUST carry `feat=FEAT_ID`, `run=RUN_ID`, `req=REQ-XXX` (or
`req=REQ-XXX,REQ-YYY` for multi-req coder tasks) labels.

```bash
RUN_ID=$(python3 -c "import uuid; print(uuid.uuid4().hex[:8])")

BD_CODER=$(bd create "Coder: <component> — <goal>" --silent \
  --labels "feat=$FEAT_ID,run=$RUN_ID,req=REQ-XXX,phase=implement,agent=coder" \
  --acceptance "<acceptance criterion>" \
  --body-file - << 'DSL'
[task id=t1 type=code]
[req id=REQ-XXX-NNN]
[c4 component=<name> container=<name>]
[component]
  <C4 L3 component description — patterns, ownership, interfaces>
[/component]
[container]
  <C4 L2 container context — tech stack, callers, callees>
[/container]
[goal]<objective>[/goal]
[why]<one sentence rationale>[/why]
[accept]<verbatim acceptance criterion>[/accept]
[non-goal]<explicit exclusions>[/non-goal]
[file read=<path>]
[out <path>]
[/task]
DSL
)

BD_TESTER=$(bd create "Tester: <component>" --silent \
  --labels "feat=$FEAT_ID,run=$RUN_ID,req=REQ-XXX,phase=implement,agent=tester" \
  --acceptance "all tests pass" \
  --body-file - << 'DSL'
[task id=t2 type=test]
[req id=REQ-XXX-NNN]
[c4 component=<name> container=<name>]
[goal]write and run tests covering [accept] from task t1[/goal]
[accept]<acceptance criterion>[/accept]
[ref t1]
[out tests/<path>]
[/task]
DSL
)
bd dep add $BD_TESTER --depends-on $BD_CODER

BD_REVIEWER=$(bd create "Reviewer: $FEAT_ID" --silent \
  --labels "feat=$FEAT_ID,run=$RUN_ID,phase=implement,agent=reviewer" \
  --acceptance "verdict: approve or request-changes" \
  --body-file - << 'DSL'
[task id=tr type=review]
[goal]review all coder output for FEAT_ID[/goal]
[accept]no crit/major findings unaddressed; verdict is approve or request-changes[/accept]
[ref t1]
[adr ref=ADR-NNN]
[/task]
DSL
)
for BD_CODER_ID in $BD_CODER_IDS; do
  bd dep add $BD_REVIEWER --depends-on $BD_CODER_ID
done
```

---

## Step 6 — Build and Return Exec Block

Build the `[exec]` block and return it to sdd:

```
[exec run=<RUN_ID> feat=<FEAT_ID>]
[job id=<BD_CODER> role=coder model=haiku|sonnet]
[job id=<BD_TESTER> role=tester model=haiku depends=<BD_CODER>]
[job id=<BD_REVIEWER> role=reviewer model=sonnet depends=<BD_CODER>]
[/exec]
```

sdd passes this to the conductor skill.

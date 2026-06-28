---
name: plan
description: >
  SDD planning skill. Validates documentation prerequisites, reads feature
  requirements and C4 context from docs, decomposes into bd tasks, presents
  a user confirmation gate, creates bd issues with enriched DSL, and hands
  off to the conductor. Called by the sdd skill after docs are approved.
  Not normally invoked directly.
---

# [origin ref=llm-dsl-l3a,llm-dsl-0p1 req=REQ-TRACER-BULLETS-001,REQ-TRACER-BULLETS-002,REQ-TRACER-BULLETS-003,REQ-TRACER-BULLETS-004 c4=sdd_skills/plan_skill]
#   [intent]Planning skill prompts for SDD pipeline: validates docs, extracts requirements and C4 context, decomposes into tracer-bullet vertical slices driven by observable behavior with prefactor identification and file-overlap dependencies[/intent]
# [/origin]

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

### 2a. Understand feature scope and decomposition strategy

Read the full feature file and understand:
- Which requirements are foundational scaffolding/infrastructure (potential prefactors)
- Which requirement represents the core happy-path slice (observable end-to-end behavior)
- Which requirements are follow-on enhancements or optional paths

For each requirement, identify what observable behavior it delivers:
- Not "implement the data layer" but "user can submit valid credentials and receive a session token"
- Not "add validation logic" but "invalid emails are rejected with clear error message"

This context drives the decomposition strategy in Step 3.

### 2b. Read all requirements for the feature

Parse `docs/specs/features/<feature-name>.rst`. Collect for each `.. req::`:
- `id` — REQ-XXX-NNN
- `rationale` → becomes `[why]`
- `acceptance` → becomes `[accept]`
- `non_goal` → becomes `[non-goal]`
- `c4_component`
- `c4_container`
- Body text → becomes the basis for `[goal]`

### 2c. Read C4 L3 component descriptions

For each unique `c4_component` referenced:

```bash
cat docs/architecture/components/<c4_component>.rst
```

Extract the component narrative (responsibility, patterns, ownership, interfaces).
This becomes `[component]` in the bd task DSL. Trim to the essential —
implementation patterns and ownership boundaries, not boilerplate.

### 2d. Read C4 L2 container context

Read the full `docs/source/architecture/containers.rst` file and extract the section
for each unique `c4_container` referenced by this feature.

Extract tech stack, callers, and callees for each container. This becomes `[container]`
in the coder task DSL. Tester and reviewer tasks do not carry `[container]` — they
read it from the coder issue via `[ref]`.

### 2e. Identify relevant ADRs

For each unique `c4_component` and `c4_container` touched by this feature,
find ADRs whose `:c4_scope:` includes that component/container id or `system`:

```bash
grep -rl ":c4_scope:.*\(system\|<component_id>\|<container_id>\)" docs/specs/adrs/
```

Also always include ADRs scoped to `system` — they apply to everything:

```bash
grep -rl ":c4_scope:.*system" docs/specs/adrs/
```

Deduplicate. Record only the matched ADR IDs. These go into the reviewer task
as `[adr ref=ADR-NNN]` entries. The reviewer reads only those files.

---

## Step 3 — Decompose into Tracer-Bullet Vertical Slices

Implement vertical slices driven by observable behavior and testable acceptance
criteria, not by layers. Order exec block as: prefactors → happy-path → remaining
slices by ascending complexity. Use file overlap to determine sequential vs. parallel
execution.

### 3a. Identify prefactor tasks

Review all requirements and classify scaffolding/infrastructure work:
- **Prefactor**: foundational infrastructure that other tasks depend on
  - Examples: database schema, auth framework setup, API transport layer, logging
  - Create with `type=prefactor`
  - Appear first in exec block
  - Coder focuses on minimal scaffolding to unblock happy-path

- **Normal**: feature work that builds directly on prefactors
  - Examples: implement user registration, add password reset flow, build admin dashboard

Classify a requirement as a prefactor if its deliverable is infrastructure that other
slices depend on to run — not based on keyword matching. Ask: "Could a slice coder
start without this?" If no, it is a prefactor.

### 3b. Frame each slice as observable behavior, not layer deliverables

For each requirement (normal or prefactor), rewrite the goal and acceptance criterion
to describe behavior, not components:

**Bad**: Goal: "Implement user DB model"; Accept: "UserModel class created"

**Good**: Goal: "User can create account with email and password"; Accept: "Given valid
email and password, when user submits registration form, then account is created and
session token returned"

Use Given/When/Then language for acceptance criteria. Make it testable the moment
the coder closes.

### 3c. Assign output file paths to each requirement

For each requirement, identify the files it will create or modify:
- Infer from `c4_component` directory structure (e.g., `skills/plan/`, `docs/`)
- Use the `[out <path>]` declarations in the generated task DSL

### 3d. Create coder tasks with vertical slices

**Default: one coder task per requirement.** Name each task uniquely (e.g., `t1`, `t2`, etc.).

For each requirement (prefactor or normal):
- Create 1 coder task covering that single requirement
- Set `type=prefactor` for prefactor requirements, `type=code` for normal requirements
- Model: see RULES.md escalation table
- Goal and accept MUST be behavior-framed (from 3b), not layer-based

**Optional: merge requirements into a single coder task if**:
- All requirements have the same `c4_component` AND
- Their `[out]` paths overlap (merging avoids a sequenced depends= between tasks that
  write the same files)

Otherwise, keep them separate (tracer-bullet slice per requirement). Requirements with
disjoint `[out]` paths do not need merging — they can run in parallel.

### 3e. Create tester tasks and wire file-overlap dependencies

**For each coder task**:
1. Create 1 tester task that depends on the coder task
2. Model: see RULES.md escalation table
3. Tester goal: "write and run tests covering observable behavior from [goal]"
4. Tester acceptance: "all tests pass; acceptance criterion from coder task verified"

**After all coder and tester tasks are planned, wire dependencies**:

1. Collect all `[out]` paths for each coder task
2. Identify the happy-path coder task (the one whose behavior validates the core
   feature goal; typically the first non-prefactor slice)
3. **Infrastructural dependency (prefactor → slice)**: every slice coder task that
   requires a prefactor's output to exist (schema, framework, service stub, etc.)
   must carry `depends=<prefactor-coder>` — regardless of whether they share output
   files. If in doubt, add the dependency.
4. **File-overlap dependency (slice → slice)**: for any two coder tasks that share at
   least one `[out]` path, add `depends=<earlier_task>` to the later task. Pair them
   with a single shared tester that depends on the later coder.
5. **Parallel execution**: coder tasks with disjoint `[out]` paths and no
   infrastructural dependency can run in parallel — NO `depends=` between them,
   each gets its own independent tester.

### 3f. Order the exec block

1. Prefactor coder tasks first (in order of logical dependency)
2. Prefactor tester tasks (in same order, each depends on its coder)
3. Happy-path coder task
4. Happy-path tester task
5. Remaining coder tasks in ascending complexity/risk order
6. Remaining tester tasks (each depends on its coder)
7. Reviewer task (depends on all coder tasks)

### 3g. Create reviewer task

Add 1 reviewer task covering the entire feature:
- Depends on all coder tasks
- Model: sonnet (opus for auth/payments/migration)

### 3h. Define the Definition of Done

- All prefactor coder tasks closed with `s=ok`
- Happy-path coder task closed with `s=ok` (end-to-end behavior validated)
- Happy-path tester task closed with `s=ok` (acceptance criterion verified)
- Remaining coder tasks closed with `s=ok`
- All tester tasks closed with `s=ok` (tests passing)
- Reviewer verdict: `approve` or `request-changes` (not `block`)
- All acceptance criteria verified on their respective slice close

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
[goal]<observable behavior>[/goal]
[why]<one sentence rationale>[/why]
[accept]<Given/When/Then acceptance criterion>[/accept]
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
[goal]write and run tests covering observable behavior from task t1[/goal]
[accept]all tests pass; Given/When/Then acceptance criterion verified[/accept]
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

<!-- [origin ref=llm-dsl-yms.3,llm-dsl-2zv1.13 req=REQ-GITHUB-ISSUES-002,REQ-GITHUB-ISSUES-003,REQ-SECURITY-REVIEW-006,REQ-SECURITY-REVIEW-003 c4=sdd_skills/sdd_orchestrator]
  [intent]Entry point for Spec-Driven Development pipeline; orchestrates docs, security-design, plan, implement, arch-review, and security-review phases with support for GitHub issue integration.[/intent]
[/origin] -->

---
name: sdd
description: >
  Spec-Driven Development entry point. Drives the full SDD pipeline
  autonomously: docs → security-design → plan → implement → arch-review → security-review → done. Takes a feature name,
  FEAT-XXX identifier, or GitHub issue number (#N). State is tracked in a bd
  epic. Resumes from current phase if the epic already exists. Resets to docs
  phase when any downstream skill surfaces a new requirement. Use whenever
  starting or continuing work on a feature.
---

# SDD Skill — Spec-Driven Development

This skill is the single entry point for all feature work. It drives the
pipeline autonomously, pausing at the three mandatory user approval
gates and at the two security-review operator pauses (design and post). Everything
else is automatic.

Read `skills/rules/RULES.md` before starting.

---

## Invocation

```
/sdd #N                            start from a GitHub issue (fetch, derive FEAT-ID)
/sdd <feature-name-or-FEAT-XXX>    start or resume a specific feature
/sdd                               resume any in-progress feature (most recent epic)
```

---

## Pipeline

```
docs → security-design → plan → implement → arch-review → security-review → done

docs ──[approve docs]──► security-design ──[operator gate]──► plan ──[approve plan]──►
  conductor ──► implement ──► arch-review ──[approve]──► security-review ──[operator gate]──► done

Any phase can reset to docs if [new-req] is discovered.
```

Three approval gates plus two security-review operator pauses (security-design
and security-review). Three reset paths plus the security resets. Everything
else is autonomous.

---

## State

State lives in the bd epic. Create one epic per feature per SDD run.

Epic labels:
- `feat=FEAT-XXX` — the feature being worked on
- `phase=docs|security-design|plan|implement|arch-review|security-review|done` — current phase;
  **exactly one** `phase=` label at all times (see Phase changes)
- `run=<run_id>` — 8-char hex run identifier
- `reset-count=<n>` — number of times the pipeline has reset to docs (every reset, including security-design and security-review resets)
- `base=<sha>` — fork point the security review diffs from; operator-confirmed at epic creation (see Base)

External reference (GitHub issue):
- `--external-ref gh-N` — link to GitHub issue (if invoked via /sdd #N)

```bash
# Create epic
EPIC_ID=$(bd create --type epic "SDD: FEAT-XXX — <feature title>")
for L in "feat=FEAT-XXX" "phase=docs" "run=$RUN_ID" "reset-count=0"; do bd label add $EPIC_ID "$L"; done   # one label per call

# Create epic with external reference (for GitHub issue integration)
EPIC_ID=$(bd create --type epic "SDD: FEAT-XXX — <feature title>" --external-ref gh-N)
for L in "feat=FEAT-XXX" "phase=docs" "run=$RUN_ID" "reset-count=0"; do bd label add $EPIC_ID "$L"; done   # one label per call

# Read current phase
bd show $EPIC_ID | grep "phase="

# Advance phase: remove the old phase label, then add the new one
OLD=$(bd show $EPIC_ID --json | grep -oP 'phase=\K[a-z-]+' | head -1)
bd label remove $EPIC_ID "phase=$OLD"
bd label add $EPIC_ID "phase=plan"
```

### Phase changes

Every phase change removes the old phase label with `bd label remove` before
adding the new one, so the epic carries exactly one `phase=` label. Verify with
`bd show $EPIC_ID --json | grep -o 'phase=[a-z-]*'` (one line). Never leave two.

### Base

At epic creation, work out the fork point: the commit the run branched from
(on a stacked branch this is NOT the merge-base with main). Ask the operator to
confirm it with AskUserQuestion, then label the epic `base=<sha>`. The security
review skill writes the confirmed base into the `Base` column of the first
review record in `docs/source/security/reviews.rst`; that record, not the label,
is the source of truth, and the label mirrors it.

### Security gate

The gate script decides whether the security state allows a move. Run it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/security_gate.py" check --feature FEAT-XXX --stage design|post --epic $EPIC_ID --main main
```

- before every move to `plan` (`--stage design`);
- before every move to `done` (`--stage post`);
- before every `bd close` of the epic (`--stage post`);
- live, when the move happens, and again on resume (see Crash Recovery).

Exit 0 is required. On non-zero, show the error lines, do not move the phase and
do not close. Never bypass it. If the epic was closed while the post check fails,
reopen it (`bd reopen $EPIC_ID`), set `phase=security-review`, and re-run the
security-review phase.

---

## Workflow

### -1. GitHub Issue Resolution (if invoked as /sdd #N)

If the user invokes `/sdd #N` with a GitHub issue number:

```bash
GITHUB_ISSUE_NUM=N
EXTERNAL_REF="gh-$GITHUB_ISSUE_NUM"

import sys
sys.path.insert(0, "$CLAUDE_PROJECT_DIR/src")
from github_bridge import fetch_issue

ISSUE_TEXT=$(python3 << 'PYEOF'
import sys
sys.path.insert(0, "$CLAUDE_PROJECT_DIR/src")
from github_bridge import fetch_issue
print(fetch_issue($GITHUB_ISSUE_NUM))
PYEOF
)

ISSUE_TITLE=$(echo "$ISSUE_TEXT" | head -1 | sed 's/^Title: //')
```

**Derive FEAT-ID from issue title:**

```bash
FEAT_ID=$(python3 -c "
import sys; sys.path.insert(0, '$CLAUDE_PROJECT_DIR/src')
from feat_id import derive_feat_id
print(derive_feat_id(sys.stdin.read().strip()))
" <<< "$ISSUE_TITLE")
```

**Present to user with override option:**

```
GitHub Issue #$GITHUB_ISSUE_NUM

Title: $ISSUE_TITLE

Derived FEAT-ID: $FEAT_ID

Confirm FEAT-ID or enter override (or blank to cancel):
```

If user approves (or provides override), proceed with the derived FEAT_ID.

---

### 0. Setup

Generate a run ID and find or create the epic:

```bash
RUN_ID=$(python3 -c "import uuid; print(uuid.uuid4().hex[:8])")

EPIC_CREATE_OPTS=""
if [ -n "$EXTERNAL_REF" ]; then
  EPIC_CREATE_OPTS="--external-ref $EXTERNAL_REF"
fi

# Check for existing epic
EPIC_ID=$(bd list --label "feat=FEAT-XXX" --type epic --status open | head -1 | awk '{print $1}')

if [ -z "$EPIC_ID" ]; then
  EPIC_ID=$(bd create --type epic $EPIC_CREATE_OPTS "SDD: FEAT-XXX — <feature title>")
  for L in "feat=FEAT-XXX" "phase=docs" "run=$RUN_ID" "reset-count=0"; do bd label add $EPIC_ID "$L"; done   # one label per call
fi

# confirm the base (fork point) with the operator, then label it
bd label add $EPIC_ID "base=<confirmed sha>"

CURRENT_PHASE=$(bd show $EPIC_ID --json | grep -oP "phase=\K[a-z-]+" | head -1)
```

Resume from `CURRENT_PHASE`. Do not re-run completed phases.

---

### Phase: docs

**Purpose**: ensure the NL specification is complete, correct, and approved
by the user before any planning work begins.

Invoke the docs skill:

```
Read skills/docs/SKILL.md and execute it for FEAT-XXX.

Context:
- FEAT_ID: FEAT-XXX
- EPIC_ID: <epic_id>
- CLAUDE_PROJECT_DIR: <project_dir>

The docs skill must run its full workflow including the approval gate.
Return one of:
  approved         — user approved, advance to plan
  reset:<reason>   — new requirement found during docs work
```

If docs skill returns `reset:<reason>`:
- Increment `reset-count` on the epic
- Re-run the docs phase

If docs skill returns `approved`:
- Remove `phase=docs`, add `phase=security-design`
- Advance to security-design phase

---

### Phase: security-design

**Purpose**: the security analyst reviews the approved design (docs) before any
planning, and the operator decides each finding at an interactive gate.

**Run it inline, in this (main-agent) context. Do NOT spawn it as a sub-agent**:
the skill spawns the analysis agent and fix workers and asks the operator
questions.

```
Read skills/security-review/SKILL.md and execute it here, in the main context.

Inputs:
- FEAT_ID: FEAT-XXX
- RUN_ID: <run_id>
- EPIC_ID: <epic_id>
- STAGE: design
- CLAUDE_PROJECT_DIR: <project_dir>

Return the [security-review-result ... signal=advance|reset|stopped] line.
```

If `signal=reset`:
- Increment `reset-count` (security-design resets count towards the 3+ escalation)
- Remove `phase=security-design`, add `phase=docs`
- Pass the "add requirement" findings to the docs phase as the first new requirements

If `signal=advance`:
- Run the security gate check (`--stage design`); it must exit 0
- Remove `phase=security-design`, add `phase=plan`
- Advance to plan phase

If `signal=stopped`: stay in `phase=security-design` and report to the user.

---

### Phase: plan

**Purpose**: validate prerequisites, decompose requirements into tasks,
get user approval, create bd issues.

Invoke the plan skill:

```
Read skills/plan/SKILL.md and execute it.

Inputs:
- FEAT_ID: FEAT-XXX
- EPIC_ID: <epic_id>
- RUN_ID: <run_id>
- EXTERNAL_REF: <gh-N or empty>
- CLAUDE_PROJECT_DIR: <project_dir>

The plan skill runs its preflight, extract, decompose, confirm gate, and
issue creation steps. Return one of:
  [exec run=... feat=... ] ... [/exec]   — plan approved, issues created
  reset:<reason>                          — preflight found missing docs
```

If plan returns `reset:<reason>`:
- Remove `phase=plan`, add `phase=docs`
- Increment `reset-count`
- Re-run from docs phase

If plan returns an `[exec]` block:
- Extract all job IDs from the [exec] block
- If EXTERNAL_REF is set, add it to each job:
  ```bash
  for JOB_ID in <extracted_ids>; do
    bd update $JOB_ID --external-ref $EXTERNAL_REF
  done
  ```
- Remove `phase=plan`, add `phase=implement`
- Advance to conductor

---

### Phase: implement (conductor)

**Purpose**: execute the plan — spawn workers, run code and tests, collect results.

**Run the conductor inline, in this (main-agent) context. Do NOT spawn it as a
sub-agent.** The conductor's whole job is to spawn worker sub-agents (coder,
tester, reviewer) via the Agent tool. Only the main agent can spawn
sub-agents — a spawned sub-agent has no Agent tool, so a conductor running one
level down cannot offload any work to the workers. That is the failure mode
this skill exists to avoid.

Invoke the conductor skill inline:

```
Read skills/conductor/SKILL.md and execute it here, in the main context.

Project directory: <CLAUDE_PROJECT_DIR>
Exec block:
<EXEC_BLOCK>

The conductor parses the [exec] block, spawns one worker sub-agent per job in
dependency-ordered waves (via the Agent tool), collects their results, and
returns a [synthesis] block. It runs in this context so it retains the Agent
tool needed to spawn workers.
```

Read the synthesis block returned by the conductor.

If `s=reset` in synthesis:
- Remove `phase=implement`, add `phase=docs`
- Increment `reset-count`
- Collect all `[new-req]` descriptions from the synthesis
- Pass them to the docs skill in the next docs phase invocation
  so they are the first thing captured
- Re-run from docs phase

If `s=ok`:
- Remove `phase=implement`, add `phase=arch-review`
- Advance to arch-review

If `s=partial` or `s=fail`:
- Report blocked issues to user
- Ask user: fix and re-run, or reset to plan?
- Act accordingly

---

### Phase: arch-review

**Purpose**: verify the implementation fits the architecture holistically.

**Run arch-review inline, in this (main-agent) context. Do NOT spawn it as a
sub-agent.** Arch-review itself spawns a test-quality reviewer sub-agent
(step 2b) and, on "fix", a coder worker (step 8). Like the conductor, it can
only do that from the main context where the Agent tool is available.

Invoke the arch-review skill inline:

```
Read skills/arch-review/SKILL.md and execute it here, in the main context.

Inputs:
- FEAT_ID: FEAT-XXX
- RUN_ID: <run_id>
- EPIC_ID: <epic_id>
- CLAUDE_PROJECT_DIR: <project_dir>
```

Read the arch-review result:

If `s=approved`:
- Arch-review does NOT close the epic or mark requirements implemented.
- Remove `phase=arch-review`, add `phase=security-review`
- Advance to security-review phase

If `s=reset`:
- Remove `phase=arch-review`, add `phase=docs`
- Increment `reset-count`
- Re-run from docs phase

---

### Phase: security-review

**Purpose**: the security analyst reviews the implemented code and the operator
decides each finding at an interactive gate. Only after this does the run finish.

**Run it inline, in this (main-agent) context. Do NOT spawn it as a sub-agent.**

```
Read skills/security-review/SKILL.md and execute it here, in the main context.

Inputs:
- FEAT_ID: FEAT-XXX
- RUN_ID: <run_id>
- EPIC_ID: <epic_id>
- STAGE: post
- CLAUDE_PROJECT_DIR: <project_dir>

Return the [security-review-result ... signal=advance|reset|stopped] line.
```

If `signal=reset` ("revise docs" or an added requirement):
- Increment `reset-count`
- Remove `phase=security-review`, add `phase=docs`
- Re-run from docs phase

If `signal=stopped`: stay in `phase=security-review` and report to the user.

If `signal=advance`:
- Run the security gate check (`--stage post`); it must exit 0
- Remove `phase=security-review`, add `phase=done`
- Run the check again immediately before `bd close $EPIC_ID`, then close the epic
- Mark the feature's requirements `status=implemented` in docs
- Report completion to user

---

### Phase: done

Report to user:

```
## SDD Complete — FEAT-XXX

Run: RUN_ID
Resets: <reset-count>

Requirements implemented:
<list of REQ-XXX-NNN with status=implemented>

Files changed:
<list of artifacts from the run>

The epic is closed only after the post security check passed. All requirements are marked implemented in docs.
```

---

## Reset Handling

A reset can be triggered from any phase. The reset counter is an indicator of
spec quality — high reset counts suggest the initial docs phase was rushed.

After a reset, the docs phase receives the new requirement descriptions as
context so the interviewer starts by capturing those first.

Maximum resets before escalating to user: none — the loop runs until done.
The count includes security-design and security-review resets.
After 3+ resets (counting every reset, security ones included), surface the pattern to the user:

```
This feature has reset N times. The recurring gap is: <pattern>.
Consider completing the full architecture interview before proceeding.
Shall I continue, or would you like to pause and complete the docs first?
```

---

## Crash Recovery

If a session ends mid-run, resume with `/sdd FEAT-XXX`. The skill reads the
epic's current phase and picks up from there.

For stalled conductor runs:

```bash
bd list --label "run=$RUN_ID" --status open
```

Before resuming, run the security gate check live again (`--stage design` when
`phase=security-design` or earlier, `--stage post` from `phase=security-review`
on) and never skip it because an earlier run passed. If the epic is closed but
the post check fails, reopen it and set `phase=security-review`.

Re-invoke from the implement phase — the conductor will re-read open issues
and resume wave execution.

---
name: sdd
description: >
  Spec-Driven Development entry point. Drives the full SDD pipeline
  autonomously: docs → plan → implement → arch-review. Takes a feature name
  or FEAT-XXX identifier. State is tracked in a bd epic. Resumes from current
  phase if the epic already exists. Resets to docs phase when any downstream
  skill surfaces a new requirement. Use whenever starting or continuing work
  on a feature.
---

# SDD Skill — Spec-Driven Development

This skill is the single entry point for all feature work. It drives the
pipeline autonomously, pausing only at the three mandatory user approval
gates. Everything between gates is automatic.

Read `skills/rules/RULES.md` before starting.

---

## Invocation

```
/sdd <feature-name-or-FEAT-XXX>    start or resume a specific feature
/sdd                               resume any in-progress feature (most recent epic)
```

---

## Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        SDD Pipeline                             │
│                                                                 │
│  docs ──[user approves docs]──► plan ──[user approves plan]──► │
│  ──► conductor ──► implement ──► arch-review ──[user approves]──► done
│                                                                 │
│  Any phase can reset to docs if [new-req] is discovered.        │
└─────────────────────────────────────────────────────────────────┘
```

Three approval gates. Three reset paths. Everything else is autonomous.

---

## State

State lives in the bd epic. Create one epic per feature per SDD run.

Epic labels:
- `feat=FEAT-XXX` — the feature being worked on
- `phase=docs|plan|implement|arch-review|done` — current phase
- `run=<run_id>` — 8-char hex run identifier
- `reset-count=<n>` — number of times the pipeline has reset to docs

```bash
# Create epic
EPIC_ID=$(bd epic create "SDD: FEAT-XXX — <feature title>")
bd epic update $EPIC_ID --label "feat=FEAT-XXX,phase=docs,run=$RUN_ID,reset-count=0"

# Read current phase
bd epic show $EPIC_ID | grep "phase="

# Advance phase
bd epic update $EPIC_ID --label "phase=plan"
```

---

## Workflow

### 0. Setup

Generate a run ID and find or create the epic:

```bash
RUN_ID=$(python3 -c "import uuid; print(uuid.uuid4().hex[:8])")

# Check for existing epic
EPIC_ID=$(bd list --label "feat=FEAT-XXX" --type epic --status open | head -1 | awk '{print $1}')

if [ -z "$EPIC_ID" ]; then
  EPIC_ID=$(bd epic create "SDD: FEAT-XXX — <feature title>")
  bd epic update $EPIC_ID --label "feat=FEAT-XXX,phase=docs,run=$RUN_ID,reset-count=0"
fi

CURRENT_PHASE=$(bd epic show $EPIC_ID | grep -oP "phase=\K[a-z-]+")
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
- Update epic: `phase=plan`
- Advance to plan phase

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
- CLAUDE_PROJECT_DIR: <project_dir>

The plan skill runs its preflight, extract, decompose, confirm gate, and
issue creation steps. Return one of:
  [exec run=... feat=... ] ... [/exec]   — plan approved, issues created
  reset:<reason>                          — preflight found missing docs
```

If plan returns `reset:<reason>`:
- Update epic: `phase=docs`
- Increment `reset-count`
- Re-run from docs phase

If plan returns an `[exec]` block:
- Update epic: `phase=implement`
- Advance to conductor

---

### Phase: implement (conductor)

**Purpose**: execute the plan — spawn workers, run code and tests, collect results.

Spawn the conductor as a sub-agent:

```python
Agent(
    model="haiku",
    description="Conductor: FEAT-XXX run RUN_ID",
    prompt=f"""
Read skills/conductor/SKILL.md and execute it.

Project directory: {CLAUDE_PROJECT_DIR}
Exec block:
{EXEC_BLOCK}
""",
    run_in_background=False
)
```

Read the synthesis block returned by the conductor.

If `s=reset` in synthesis:
- Update epic: `phase=docs`
- Increment `reset-count`
- Collect all `[new-req]` descriptions from the synthesis
- Pass them to the docs skill in the next docs phase invocation
  so they are the first thing captured
- Re-run from docs phase

If `s=ok`:
- Update epic: `phase=arch-review`
- Advance to arch-review

If `s=partial` or `s=fail`:
- Report blocked issues to user
- Ask user: fix and re-run, or reset to plan?
- Act accordingly

---

### Phase: arch-review

**Purpose**: verify the implementation fits the architecture holistically.

Spawn the arch-review as a sub-agent:

```python
Agent(
    model="sonnet",
    description="Arch-review: FEAT-XXX run RUN_ID",
    prompt=f"""
Read skills/arch-review/SKILL.md and execute it.

Inputs:
- FEAT_ID: FEAT-XXX
- RUN_ID: {RUN_ID}
- EPIC_ID: {EPIC_ID}
- CLAUDE_PROJECT_DIR: {CLAUDE_PROJECT_DIR}
""",
    run_in_background=False
)
```

Read the arch-review result:

If `s=approved`:
- Update epic: `phase=done`
- Close epic: `bd epic close $EPIC_ID`
- Report completion to user

If `s=reset`:
- Update epic: `phase=docs`
- Increment `reset-count`
- Re-run from docs phase

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

The epic is closed. All requirements are marked implemented in docs.
```

---

## Reset Handling

A reset can be triggered from any phase. The reset counter is an indicator of
spec quality — high reset counts suggest the initial docs phase was rushed.

After a reset, the docs phase receives the new requirement descriptions as
context so the interviewer starts by capturing those first.

Maximum resets before escalating to user: none — the loop runs until done.
But after 3+ resets, surface the pattern to the user:

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

Re-invoke from the implement phase — the conductor will re-read open issues
and resume wave execution.

---
name: llm-dsl
description: >
  Default orchestration skill for any non-trivial task in this project. The main
  agent (sonnet/opus) acts as conductor only — it NEVER does the work itself.
  All work is delegated to Claude sub-agents (haiku or sonnet) via the Agent
  tool, tracked via bd issues, and communicated in compact LLM-DSL. Use for ANY
  task that produces output: code changes, file analysis, research, review,
  testing. Skip ONLY for pure Q&A or one-line factual answers where no file
  changes or structured output are needed.
---

# LLM-DSL Skill

## Mandatory Workflow (all six steps, in order)

```
1. UNDERSTAND  — describe the problem in project context
2. SCOPE       — state what is in and out of scope
3. PLAN        — decompose into tasks, each with acceptance criteria; define DoD
4. CONFIRM     — present 1-3 to user, ask "shall I proceed?", WAIT for go-ahead
5. EXECUTE     — create bd issues, spawn sub-agents
6. SYNTHESIZE  — verify against DoD, report to user
```

**Never skip or reorder steps. Never start step 5 without explicit user approval.**

---

## Step 1 — Understand

Read the user's request and describe:
- What problem is being solved
- Where it sits in the project (which files, which layer, which agent role)
- What currently exists that's relevant (read files if needed)
- Any ambiguities that need resolving before planning

Keep this to 3-5 sentences. Resolve ambiguities by asking — do not assume.

---

## Step 2 — Scope

State explicitly:

**In scope:**
- Bullet list of what will be changed or produced

**Out of scope:**
- Bullet list of adjacent things that will NOT be touched
- Be specific: "will not refactor existing validation logic", "will not update tests outside src/validation/"

This boundary is binding. Sub-agents must stay inside it.

---

## Step 3 — Plan

### Task decomposition

Decide how many workers are needed:
- **Single focused task** → one haiku sub-agent
- **Multi-step / parallel** → decompose into coder + reviewer + tester (or subset)

For each task, define:
- Goal (one sentence)
- Input files or prior task references
- Expected output artifacts
- **Acceptance criteria** (mandatory — one or more verifiable conditions)

### Definition of Done (DoD)

State what the overall workflow succeeds at — the integration-level check
the main agent performs after all workers complete. Example:
> "Email validation is implemented, passes all new tests, and reviewer approves with no critical findings."

### Model selection

| Role | Model | When to use sonnet instead |
|------|-------|---------------------------|
| coder | `haiku` | Multi-file refactor, architectural changes |
| reviewer | `sonnet` | Always |
| tester | `haiku` | Complex strategy, edge-case analysis |

---

## Step 4 — Confirm (hard gate)

Present a summary of steps 1-3 to the user:

```
## Understanding
<1-2 sentences>

## Scope
In: ...
Out: ...

## Plan
Task 1 — <role>: <goal>
  Acceptance: <criteria>
Task 2 — <role>: <goal>
  Acceptance: <criteria>
...

## Definition of Done
<sentence>

Shall I proceed?
```

**Stop here. Do not continue until the user replies with approval.**

If the user requests changes, update the plan and confirm again before proceeding.

---

## Step 5 — Execute

Only reached after explicit user approval.

### Create bd issues

```bash
RUN_ID=$(python3 -c "import uuid; print(uuid.uuid4().hex[:8])")

BD_CODER=$(python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "Implement: Add email validation" \
  --agent coder --run-id "$RUN_ID" \
  --acceptance "validate_email() exists in src/validation/email.py" \
  --acceptance "rejects malformed addresses, accepts valid ones" \
  --body '[task id=t1 type=code]
[goal]Add email validation to signup[/goal]
[out src/validation/email.py]
[/task]')

BD_REVIEWER=$(python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "Review: email validation" \
  --agent reviewer --run-id "$RUN_ID" \
  --depends-on "$BD_CODER" \
  --acceptance "no critical or major findings" \
  --body '[task id=t2 type=review]
[goal]Review email validation for correctness and security[/goal]
[ref t1.artifacts]
[/task]')

BD_TESTER=$(python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "Test: email validation" \
  --agent tester --run-id "$RUN_ID" \
  --depends-on "$BD_CODER" \
  --acceptance "all tests pass" \
  --acceptance "edge cases covered: empty, malformed, unicode" \
  --body '[task id=t3 type=test]
[goal]Write and run tests for email validation[/goal]
[ref t1.artifacts]
[/task]')
```

### Spawn sub-agents

```python
# Coder — foreground (reviewer + tester depend on it)
Agent(model="haiku", description="Coder: email validation",
      prompt=<sub_agent_prompt(BD_CODER, "coder")>,
      run_in_background=False)

# Reviewer + tester — parallel
Agent(model="sonnet", description="Reviewer: email validation",
      prompt=<sub_agent_prompt(BD_REVIEWER, "reviewer")>,
      run_in_background=True)
Agent(model="haiku", description="Tester: email validation",
      prompt=<sub_agent_prompt(BD_TESTER, "tester")>,
      run_in_background=True)
```

### Sub-agent prompt template

```
You are a <role> sub-agent. Your task is in bd issue <bd_id>.

1. Read your task and acceptance criteria:
   bd show <bd_id>

2. Do the work described in [goal], staying within the scope of this issue only:
   coder    → implement code changes
   reviewer → read files in [ref], produce findings
   tester   → write + run tests, report counts

3. Verify your work meets the acceptance criteria before writing the result.

4. Write result:
   bd update <bd_id> --body-file - << 'DSL'
   [result id=<task_id> s=ok]
   [artifact path=<path> a=new|mod|del n=<lines>]
   [added fn=<name> in:<type> out:<type>]
   [suite t=<N> p=<N> f=<N>]
   [verdict approve|request-changes|block]
   [note sev=crit|major|minor|info at=<file>:<line>]<text>[/note]
   [/result]
   DSL

5. Close: bd close <bd_id>

Rules:
- Do NOT create additional bd issues or touch files outside your task scope
- If you cannot meet the acceptance criteria: write s=blocked, explain why
- Do NOT proceed past your scope even if you see related issues
```

### Crash recovery

```bash
bd list --label "run=$RUN_ID" --status open   # find stalled issues
# Re-spawn the Agent with the same bd_id — sub-agent re-reads and resumes
```

---

## Step 6 — Synthesize

Collect all results:

```bash
bd show <bd_id> | python3 .claude/skills/llm-dsl/scripts/dsl_parse.py --pretty
```

Check against the Definition of Done:
- Did all acceptance criteria pass?
- Any critical/major findings from reviewer?
- Any test failures?

Report to user in plain NL:
- What was done (files changed, functions added)
- Test results (pass/fail counts)
- Review verdict and any findings
- Whether the DoD was met
- Any action items if DoD was not met

---

## DSL Format Reference

### Task (main agent → worker)

```
[task id=<id> type=code|review|test]
[goal]<objective>[/goal]
[file read=<path>]           # file to read (multiple allowed)
[spec]...[/spec]             # structured constraints
[ref <prior-task>.artifacts] # reference prior output
[out <path>]                 # expected output file
[/task]
```

### Result (worker → main agent)

```
[result id=<id> s=ok|partial|fail|blocked]
[artifact path=<path> a=new|mod|del n=<lines>]
[added fn=<name> in:<type> out:<type>]
[removed fn=<name>]
[suite t=<total> p=<pass> f=<fail>]
  [test name=<name> s=pass|fail reason=<text>]
[/suite]
[verdict approve|request-changes|block]
[note sev=crit|major|minor|info at=<file>:<line>]<text>[/note]
[/result]
```

**Attribute quick-ref:**

| Abbrev | Meaning |
|--------|---------|
| `s=` | status: `ok` / `fail` / `blocked` / `partial` |
| `a=` | file action: `new` / `mod` / `del` |
| `n=` | line count |
| `t=` `p=` `f=` | suite total / pass / fail |
| `sev=` | severity: `crit` / `major` / `minor` / `info` |
| `at=` | file:line location |

---

## Common bd Commands

```bash
bd show <id>                                 # Read issue + body + acceptance criteria
bd list --label agent=coder                  # Filter by role
bd list --label "run=$RUN_ID" --status open  # Find stalled issues
bd ready                                     # Unblocked issues
bd blocked                                   # Blocked issues
bd dep add <child> --depends-on <parent>
bd close <id>
```

## Helper Scripts

```bash
# Create bd issue with acceptance criteria
python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "..." --agent coder --run-id "$RUN_ID" \
  --acceptance "condition 1" --acceptance "condition 2" \
  --body '[task ...]'

# Parse DSL → JSON
bd show <id> | python3 .claude/skills/llm-dsl/scripts/dsl_parse.py --pretty

# Validate DSL
python3 .claude/skills/llm-dsl/scripts/dsl_validate.py --file task.txt

# Collect molecule results
python3 .claude/skills/llm-dsl/scripts/bd_collect.py --mol-id <mol_id> --pretty
```

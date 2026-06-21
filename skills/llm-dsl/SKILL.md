---
name: llm-dsl
description: >
  Default orchestration skill for any non-trivial task in this project. Main
  agent plans, scopes, confirms with user, creates bd issues, then spawns a
  haiku conductor-execute sub-agent to run the worker loop. Workers (haiku or
  sonnet) do the actual code/review/test work, tracked via bd issues and
  communicated in compact LLM-DSL. Use for ANY task that produces output: code
  changes, file analysis, research, review, testing. Skip ONLY for pure Q&A or
  one-line factual answers.
---

# LLM-DSL Skill

## Conductor Output Rules (Strict)

- **Steps 1-3: NO user-facing text.** Do not narrate, summarize, or explain. Produce only the Step 4 block.
- **Step 4:** confirm block in the exact fixed format below. Nothing before or after it.
- **Step 5:** one status line only: "Spawning executor (run=<id>)..."
- **Step 6:** structured synthesis report only. No padding, no preamble.

---

## Mandatory Workflow (all six steps, in order)

```
1. UNDERSTAND      — (silent) describe the problem in project context
2. SCOPE           — (silent) state what is in and out of scope
3. PLAN            — (silent) decompose into tasks, each with acceptance criteria; define DoD
4. CONFIRM         — (fixed format) present 1-3 to user, ask "shall I proceed?", WAIT for go-ahead
5. EXECUTE         — create bd issues, spawn conductor-execute
6. SYNTHESIZE      — verify against DoD, report to user
```

**Never skip or reorder steps. Never start step 5 without explicit user approval.**

The main agent handles Steps 1-5. Step 5 spawns a conductor-execute sub-agent (haiku) that drives the worker loop: spawn workers in dependency order, collect results, return synthesis DSL. Main agent reads synthesis DSL and reports to user (Step 6).

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

### Setup

```bash
RUN_ID=$(python3 -c "import uuid; print(uuid.uuid4().hex[:8])")
```

### Create bd issues

```bash
BD_CODER=$(bd create "Implement: Add email validation" --silent \
  --labels "agent=coder,run=$RUN_ID" \
  --acceptance "validate_email() exists in src/validation/email.py" \
  --acceptance "rejects malformed addresses, accepts valid ones" \
  --body-file - << 'DSL'
[task id=t1 type=code]
[goal]Add email validation to signup[/goal]
[out src/validation/email.py]
[/task]
DSL
)

BD_REVIEWER=$(bd create "Review: email validation" --silent \
  --labels "agent=reviewer,run=$RUN_ID" \
  --deps "$BD_CODER" \
  --acceptance "no critical or major findings" \
  --body-file - << 'DSL'
[task id=t2 type=review]
[goal]Review email validation for correctness and security[/goal]
[ref t1.artifacts]
[/task]
DSL
)

BD_TESTER=$(bd create "Test: email validation" --silent \
  --labels "agent=tester,run=$RUN_ID" \
  --deps "$BD_CODER" \
  --acceptance "all tests pass" \
  --acceptance "edge cases covered: empty, malformed, unicode" \
  --body-file - << 'DSL'
[task id=t3 type=test]
[goal]Write and run tests for email validation[/goal]
[ref t1.artifacts]
[/task]
DSL
)
```

### Spawn conductor-execute

After creating bd issues, build the exec block and spawn the conductor-execute sub-agent:

```python
EXEC_BLOCK = """
[exec run={RUN_ID}]
[job id={BD_CODER} role=coder model=haiku]
[job id={BD_REVIEWER} role=reviewer model=sonnet depends={BD_CODER}]
[job id={BD_TESTER} role=tester model=haiku depends={BD_CODER}]
[/exec]
"""

Agent(model="haiku", description="Conductor-execute",
      prompt=<conductor_execute_prompt(EXEC_BLOCK, CLAUDE_PROJECT_DIR)>,
      run_in_background=False)
```

### Conductor-execute prompt template

```
You are a conductor-execute sub-agent. Run a pre-planned set of bd tasks in dependency order.

Project directory: <CLAUDE_PROJECT_DIR>
All file reads and writes must be inside this directory.
Run all shell commands from this directory.

Your exec block:
<EXEC_BLOCK>

Instructions:
1. Parse the [exec] block to get the list of [job] entries.
2. Spawn workers in dependency order:
   - Jobs with no depends: spawn in parallel (run_in_background=True)
   - Jobs with depends: wait for dependency to complete first (run_in_background=False)
   - Use the model specified in model= attribute
   - Use the worker sub-agent prompt template below for each job
3. After all workers complete, collect results:
   bd show <id> for each job
4. Return synthesis DSL:
   [synthesis run=<run_id> s=ok|partial|fail]
   [job id=<id> role=<role> s=ok|fail]
   [/synthesis]

Worker sub-agent prompt template:
---
You are a <role> sub-agent. Your task is in bd issue <bd_id>.

Project directory: <CLAUDE_PROJECT_DIR>
All file reads and writes must be inside this directory.
Run all shell commands from this directory.

1. Read your task and acceptance criteria:
   bd show <bd_id>

2. Do the work described in [goal], staying within the scope of this issue only.

3. Verify your work meets every acceptance criterion before writing the result.

4. Write result:
   bd update <bd_id> --body-file - << 'DSL'
   [result id=<task_id> s=ok|partial|fail|blocked]
   [artifact path=<path> a=new|mod|del n=<lines>]
   [suite t=<N> p=<N> f=<N>]
   [verdict approve|request-changes|block]
   [note sev=crit|major|minor|info at=<file>:<line>]<text>[/note]
   [/result]
   DSL

5. Close: bd close <bd_id>

Rules:
- Do NOT create additional bd issues
- Do NOT touch files outside your task scope
- If you cannot meet any acceptance criterion: write s=blocked, explain why
---
```

### Crash recovery

```bash
bd list --label "run=$RUN_ID" --status open   # find stalled issues
# Re-spawn the Agent with the same bd_id — sub-agent re-reads and resumes
```

---

## Step 6 — Synthesize

After conductor-execute returns the synthesis DSL, the main agent:

1. Parses the synthesis block to check job statuses
2. Reads each job's bd issue to collect detailed results
3. Checks against the Definition of Done:
   - Did all acceptance criteria pass?
   - Any critical/major findings from reviewer?
   - Any test failures?
4. Reports to user in plain NL:
   - What was done (files changed, functions added)
   - Test results (pass/fail counts)
   - Review verdict and any findings
   - Whether the DoD was met
   - Any action items if DoD was not met

---

## Model Selection Framework

### Default model assignment

| Role | Default model |
|------|--------------|
| coder | haiku |
| reviewer | sonnet |
| tester | haiku |

### Escalation rules (main agent decides at Step 3)

**Escalate coder to sonnet when:**
- Multi-file refactor touching >3 files
- auth / payments / security-critical code
- New module or architectural boundary

**Escalate reviewer to opus when:**
- auth, payments, or data migration changes
- Public API surface changes

Model is encoded in the `[exec]` block `[job model=...]` attribute. Conductor-execute reads and applies it — no heuristics in the executor.

---

## Code Style for Sub-Agents

Sub-agents generating code MUST follow these rules. No exceptions.

### Naming

- Functions: `snake_case`, abbreviated but inferrable (`val_email` not `validate_email_address`)
- Classes: `PascalCase`, abbreviated (`EmailVal` not `EmailValidator`)
- Local variables: Go-style short (`n`, `r`, `buf`, `err`, `ok`, `fn`, `val`, `idx`)

### Comments and docs

- No docstrings. Ever.
- No inline comments.
- Type hints on public functions only. Not on private helpers, not on local variables.

### Formatting

- No blank lines between class methods.
- Single blank line between top-level functions.
- f-strings only for string interpolation.
- MUST use list/dict comprehensions instead of explicit loops for single-line operations.
- Use `...` not `pass` in stubs or abstract methods.
- Imports: no blank lines between import groups (stdlib, third-party, local all contiguous).

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

### Exec (main agent → conductor-execute)

```
[exec run=<run_id>]
[job id=<bd_id> role=coder|reviewer|tester model=haiku|sonnet|opus]
[job id=<bd_id> role=reviewer model=sonnet depends=<bd_id>]
[/exec]
```

### Synthesis (conductor-execute → main agent)

```
[synthesis run=<run_id> s=ok|partial|fail]
[job id=<bd_id> role=<role> s=ok|fail]
[/synthesis]
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

## Developer Scripts

These scripts live in `skills/llm-dsl/scripts/` and are useful for local development and debugging. They are not called by the conductor during normal skill execution.

```bash
# Parse DSL → JSON (debugging)
bd show <id> | python3 skills/llm-dsl/scripts/dsl_parse.py --pretty

# Validate DSL syntax
python3 skills/llm-dsl/scripts/dsl_validate.py --file task.txt

# Collect all results in a molecule
python3 skills/llm-dsl/scripts/bd_collect.py --mol-id <mol_id> --pretty
```

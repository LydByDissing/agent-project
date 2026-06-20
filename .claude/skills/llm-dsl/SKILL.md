---
name: llm-dsl
description: >
  Multi-agent workflow orchestration using LLM-DSL and bd (beads) issue tracker,
  with real Claude sub-agents spawned via the Agent tool. Use when decomposing a
  task into parallel worker roles (coder, reviewer, tester), where each worker is
  a Claude sub-agent (haiku or sonnet) that reads its task from a bd issue, does
  the work, writes a DSL result back, and closes the issue. The main agent
  (sonnet/opus) orchestrates and synthesizes. Do NOT use for short messages,
  quick status updates, or simple single-step questions.
---

# LLM-DSL Skill

## When to Use

Use when:
- A task benefits from parallel worker roles (code + review + test)
- Messages contain structured data: file paths, line numbers, test results, findings
- You want token-efficient inter-agent communication

Skip when:
- Content is < 50 tokens — DSL bracket overhead exceeds savings
- It's a quick status update or one-liner response

---

## Architecture

```
Main agent (sonnet/opus)
  ├── Decompose task → DSL [task] blocks
  ├── Create bd issues (one per worker)
  ├── Spawn sub-agents via Agent tool ──► haiku or sonnet
  │     Each sub-agent:
  │       1. bd show <id>          → read [task] DSL
  │       2. Do the work
  │       3. bd update <id> body   → write [result] DSL
  │       4. bd close <id>
  ├── Collect results from bd issues
  └── Synthesize → NL summary to user
```

### Model Selection

| Worker role | Default | Use sonnet when |
|-------------|---------|-----------------|
| `coder`     | `haiku` | Multi-file refactor, complex logic |
| `reviewer`  | `sonnet` | Always — reasoning is the job |
| `tester`    | `haiku` | Simple test gen |
| `tester`    | `sonnet` | Complex strategy, edge-case analysis |

Main agent is already sonnet/opus — no change needed.

---

## Step-by-Step Orchestration

### 1. Decompose into DSL task blocks

```
[task id=t1 type=code]
[goal]Add email validation to signup[/goal]
[file read=src/handlers/user.py]
[spec][field name=email required=true rule=format:email][/spec]
[output-artifact path=src/validation/email.py]
[/task]

[task id=t2 type=review]
[goal]Review email validation implementation[/goal]
[context-ref id=t1.artifacts]
[/task]

[task id=t3 type=test]
[goal]Write tests for email validation[/goal]
[context-ref id=t1.artifacts]
[/task]
```

### 2. Create bd issues

Use `bd_create_task.py` instead of raw `bd create` — it handles quoting, labels, and deps cleanly.
Always pass `--run-id` with a short unique ID (e.g. a timestamp or UUID prefix) so you can recover
stalled issues later.

```bash
RUN_ID=$(date +%s)   # or: python3 -c "import uuid; print(uuid.uuid4().hex[:8])"

BD_CODER=$(python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "Implement: Add email validation" \
  --agent coder \
  --run-id "$RUN_ID" \
  --body '[task id=t1 type=code]
[goal]Add email validation to signup[/goal]
[output-artifact path=src/validation/email.py]
[/task]')

BD_REVIEWER=$(python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "Review: email validation" \
  --agent reviewer \
  --run-id "$RUN_ID" \
  --depends-on "$BD_CODER" \
  --body '[task id=t2 type=review]
[goal]Review email validation[/goal]
[context-ref id=t1.artifacts]
[/task]')
```

### 3. Spawn sub-agents via Agent tool

Spawn the coder first (foreground), then reviewer + tester in parallel:

```python
# Coder — foreground, must finish before review/test can start
Agent(
  description="Coder: Add email validation",
  model="haiku",
  prompt=sub_agent_prompt(bd_id=BD_CODER, role="coder"),
  run_in_background=False
)

# Reviewer and tester — parallel, both read coder artifacts
Agent(
  description="Reviewer: email validation",
  model="sonnet",
  prompt=sub_agent_prompt(bd_id=BD_REVIEWER, role="reviewer"),
  run_in_background=True
)
Agent(
  description="Tester: email validation",
  model="haiku",
  prompt=sub_agent_prompt(bd_id=BD_TESTER, role="tester"),
  run_in_background=True
)
```

### Sub-agent prompt template

Give each sub-agent exactly this structure:

```
You are a <role> sub-agent. Your task is in bd issue <bd_id>.

1. Read your task:
   bd show <bd_id>
   The body contains a [task] DSL block. Follow it exactly.

2. Complete the work described in [goal].
   Coder:    implement the code changes
   Reviewer: read the artifacts in [context-ref], produce findings
   Tester:   write and run tests, report pass/fail counts

3. Write your result:
   bd update <bd_id> --body-file - << 'DSL'
   [result id=<task_id> status=complete]
   [artifact type=file path=<path> action=created|modified lines=<N>]
   [added fn=<name> in:<type> out:<type>]
   [/result]
   DSL

4. Close the issue:
   bd close <bd_id>

Rules:
- Do NOT create additional bd issues
- If blocked: write status=blocked and explain in the result body
- Do NOT communicate outside this issue
```

### 4. Collect and synthesize

After all sub-agents complete, collect results:

```bash
bd show <bd_id> | python3 .claude/skills/llm-dsl/scripts/dsl_parse.py --pretty
```

Write a short NL summary to the user:
- What changed (files, functions added/removed)
- Review verdict and any findings
- Test results (pass/fail counts)
- Action items if any workers returned `status=blocked` or `status=failed`

### Crash recovery

If a sub-agent dies before closing its issue, find all stalled issues from this run:

```bash
bd list --label "run=$RUN_ID" --status open
```

Any open issue with your run ID is a candidate for retry or manual inspection.
Reopen the Agent call with the same bd_id — the sub-agent will re-read the issue and resume.

---

## DSL Format Reference

### Task

```
[task id=<id> type=code|review|test]
[goal]<objective>[/goal]
[file read=<path>]
[spec]...[/spec]
[context-ref id=<ref>]
[output-artifact path=<path>]
[/task]
```

### Result

```
[result id=<id> status=complete|partial|failed|blocked]
[artifact type=file path=<path> action=created|modified|deleted lines=<N>]
[added fn=<name> in:<type> out:<type>]
[removed fn=<name>]
[test-suite total=<N> pass=<N> fail=<N>]
  [test name=<name> status=pass|fail reason=<text>]
[/test-suite]
[verdict approve|request-changes|block]
[finding severity=critical|major|minor|info path=<file>:<line>]<text>[/finding]
[/result]
```

---

## Common bd Commands

```bash
bd show <id>                                # Read issue + body
bd list --label agent=coder                 # By role
bd ready                                    # Unblocked issues
bd blocked                                  # Blocked issues
bd dep add <child> --depends-on <parent>    # Add dependency
bd close <id>                               # Complete issue
bd mol pour <formula> --var key=val         # Pour a molecule
bd mol progress <mol_id>                    # Check progress
```

## Helper Scripts

```bash
# Create a bd issue with DSL body (preferred over raw bd create)
python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "Implement: X" --agent coder --run-id "$RUN_ID" --body '[task ...]'

# Parse DSL from bd show output → JSON
bd show <id> | python3 .claude/skills/llm-dsl/scripts/dsl_parse.py --pretty

# Validate DSL
python3 .claude/skills/llm-dsl/scripts/dsl_validate.py --file task.txt

# Collect all results from a molecule
python3 .claude/skills/llm-dsl/scripts/bd_collect.py --mol-id <mol_id> --pretty
```

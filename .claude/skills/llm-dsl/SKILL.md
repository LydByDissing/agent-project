---
name: llm-dsl
description: >
  Default orchestration skill for any non-trivial task in this project. The main
  agent (sonnet/opus) acts as conductor only — it NEVER does the work itself.
  All work is delegated to Claude sub-agents (haiku or sonnet) via the Agent
  tool, tracked via bd issues, and communicated in compact LLM-DSL. Use for ANY
  task that produces output: code changes, file analysis, research, review,
  testing. Routes internally: single tasks go to one haiku worker; multi-step
  tasks fan out to parallel workers. Skip ONLY for pure Q&A or one-line factual
  answers where no file changes or structured output are needed.
---

# LLM-DSL Skill

## Routing Decision (resolve before anything else)

```
Is this a factual question or one-liner with no file output?
  YES → answer directly, skip this skill
  NO  → continue ↓

Is this a single focused task (one file, one topic, one goal)?
  YES → spawn ONE haiku sub-agent with a [task] DSL, collect result
  NO  → decompose into parallel workers (coder + reviewer + tester, etc.)
```

The main agent never writes code, reads files for analysis, or runs tests itself.
That work always goes to a sub-agent.

---

## Architecture

```
Main agent (sonnet/opus) — conductor only
  ├── Route: single vs multi-step
  ├── Create bd issues (one per worker)
  ├── Spawn sub-agents via Agent tool
  │     haiku  → focused code/test work
  │     sonnet → review, complex reasoning
  │     Each sub-agent:
  │       1. bd show <id>         → read [task] DSL
  │       2. Do the work
  │       3. bd update <id> body  → write [result] DSL
  │       4. bd close <id>
  ├── Collect results: bd show <id> | dsl_parse.py
  └── Synthesize → short NL summary to user
```

### Model Selection

| Role | Model | Rationale |
|------|-------|-----------|
| coder | `haiku` | Fast, cheap; sufficient for focused edits |
| coder | `sonnet` | Multi-file refactor, architectural changes |
| reviewer | `sonnet` | Reasoning-heavy; haiku misses subtle issues |
| tester | `haiku` | Routine test generation |
| tester | `sonnet` | Complex test strategy, edge-case analysis |

---

## Orchestration: Step by Step

### 1. Decompose into DSL task blocks

```
[task id=t1 type=code]
[goal]Add email validation to signup[/goal]
[file read=src/handlers/user.py]
[spec][field name=email required=true rule=format:email][/spec]
[out src/validation/email.py]
[/task]

[task id=t2 type=review]
[goal]Review email validation implementation[/goal]
[ref t1.artifacts]
[/task]

[task id=t3 type=test]
[goal]Write tests for email validation[/goal]
[ref t1.artifacts]
[/task]
```

### 2. Create bd issues

Always pass `--run-id` for crash recovery.

```bash
RUN_ID=$(python3 -c "import uuid; print(uuid.uuid4().hex[:8])")

BD_CODER=$(python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "Implement: Add email validation" \
  --agent coder --run-id "$RUN_ID" \
  --body '[task id=t1 type=code]
[goal]Add email validation to signup[/goal]
[out src/validation/email.py]
[/task]')

BD_REVIEWER=$(python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "Review: email validation" \
  --agent reviewer --run-id "$RUN_ID" \
  --depends-on "$BD_CODER" \
  --body '[task id=t2 type=review]
[goal]Review email validation[/goal]
[ref t1.artifacts]
[/task]')
```

### 3. Spawn sub-agents

Foreground for blocking dependencies; background for parallel workers:

```python
# Blocking: coder must finish before review/test
Agent(model="haiku", description="Coder: email validation",
      prompt=<sub_agent_prompt>, run_in_background=False)

# Parallel: reviewer and tester are independent of each other
Agent(model="sonnet", description="Reviewer: email validation",
      prompt=<sub_agent_prompt>, run_in_background=True)
Agent(model="haiku", description="Tester: email validation",
      prompt=<sub_agent_prompt>, run_in_background=True)
```

**Sub-agent prompt template:**

```
You are a <role> sub-agent. Your task is in bd issue <bd_id>.

1. Read: bd show <bd_id>
   Follow the [task] DSL in the body exactly.

2. Do the work described in [goal]:
   coder    → implement code changes
   reviewer → read files in [ref], produce findings
   tester   → write + run tests, report counts

3. Write result:
   bd update <bd_id> --body-file - << 'DSL'
   [result id=<task_id> s=ok]
   [artifact path=<path> a=mod n=<lines>]
   [added fn=<name> in:<type> out:<type>]
   [/result]
   DSL

4. Close: bd close <bd_id>

Rules: no extra bd issues; if blocked write s=blocked + reason.
```

### 4. Collect and synthesize

```bash
bd show <bd_id> | python3 .claude/skills/llm-dsl/scripts/dsl_parse.py --pretty
```

Write a short NL summary: what changed, verdict, test counts, any action items.

### Crash recovery

```bash
bd list --label "run=$RUN_ID" --status open   # find stalled issues
# Re-spawn the Agent with the same bd_id — sub-agent re-reads and resumes
```

---

## DSL Format Reference

Tags keep readability where it matters for haiku workers; attrs are abbreviated
since the main agent (sonnet) synthesizes results.

### Task (input to worker)

```
[task id=<id> type=code|review|test]
[goal]<objective>[/goal]
[file read=<path>]          # file to read (multiple allowed)
[spec]...[/spec]            # structured constraints
[ref <prior-task>.artifacts] # reference prior output
[out <path>]                # expected output file
[/task]
```

### Result (output from worker)

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
| `s=` | status (`ok` / `fail` / `blocked` / `partial`) |
| `a=` | file action (`new` / `mod` / `del`) |
| `n=` | line count |
| `t=` `p=` `f=` | suite total / pass / fail |
| `sev=` | severity (`crit` / `major` / `minor` / `info`) |
| `at=` | file:line location |

---

## Common bd Commands

```bash
bd show <id>                                # Read issue + body
bd list --label agent=coder                 # Filter by role
bd list --label "run=$RUN_ID" --status open # Find stalled issues
bd ready                                    # Unblocked issues
bd blocked                                  # Blocked issues
bd dep add <child> --depends-on <parent>
bd close <id>
```

## Helper Scripts

```bash
# Create bd issue (preferred over raw bd create)
python3 .claude/skills/llm-dsl/scripts/bd_create_task.py \
  --title "..." --agent coder --run-id "$RUN_ID" --body '[task ...]'

# Parse DSL → JSON
bd show <id> | python3 .claude/skills/llm-dsl/scripts/dsl_parse.py --pretty

# Validate DSL
python3 .claude/skills/llm-dsl/scripts/dsl_validate.py --file task.txt

# Collect molecule results
python3 .claude/skills/llm-dsl/scripts/bd_collect.py --mol-id <mol_id> --pretty
```

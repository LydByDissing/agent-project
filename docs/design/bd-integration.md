# BD Integration Design

## Core Principle

**Agents talk DSL-to-DSL. Humans read DSL summaries. No static NL translation needed.**

The `bd` CLI is the interface. Issues contain DSL. Subagents produce DSL results.
The main agent reads DSL from `bd show` and produces a summary — in DSL.

## Data Flow

```
User (NL) → Main Agent (LLM)
                ↓ bd create
           [DSL task issues]
                ↓ agents pick up from bd ready
           [DSL result issues]
                ↓ bd show
           Main Agent reads DSL results
                ↓
           [DSL summary issue]
                ↓
User reads DSL summary
```

## Issue Body Format

### Task Issue (created by main agent)

```markdown
[task id=t1 type=code]
[goal]Add input validation to POST /users endpoint[/goal]
[file read=src/handlers/user.py]
[spec]
[field name=email required=true rule=format:email]
[field name=name required=true rule=length:max=100]
[field name=age required=false type=int rule=range:0-150]
[/spec]
[/task]

## Acceptance

[accept]
[check]Code implements the specified requirements[/check]
[check]All output files created/modified[/check]
[check]No syntax errors[/check]
[/accept]
```

### Result Issue (updated by subagent)

```markdown
[result id=t1 s=ok]
[artifact a=mod n=+23 path=src/handlers/user.py]
[artifact a=new n=18 path=src/validation/user_schema.py]
[added fn=validate_user_input in:RequestBody out:ValidationResult]
[complexity delta="+2cyclomatic"]
[/result]
```

### Summary Issue (created by main agent)

```markdown
[summary id=s1 s=ok]
[agent s=ok type=coder]
  [files added=21 changed=2 removed=0]
  [artifacts a=mod path=src/handlers/user.py]
  [artifacts a=new path=src/validation/user_schema.py]
[/agent]
[agent s=ok type=reviewer]
  [verdict approve]
  [findings count=1 sev=minor]
[/agent]
[agent s=ok type=tester]
  [tests f=1 p=7 t=8]
  [failures name=test_sql_injection reason="input not sanitized"]
[/agent]
[action-items]
[item]Consider using email-validator library for international domains[/item]
[item]Add input sanitization for SQL characters in name field[/item]
[/action-items]
[/summary]
```

## BD Commands

```bash
# Create task
bd create "Implement: Add validation" \
  --labels "agent=coder" \
  --body-file - <<'EOF'
[task id=t1 type=code]...[/task]
EOF

# Wire dependencies
bd dep add llm-dsl-yyy --on llm-dsl-xxx

# Subagent updates result
bd update llm-dsl-xxx --body-file - <<'EOF'
[result id=t1 s=ok]...[/result]
EOF

# Subagent closes
bd close llm-dsl-xxx

# Main agent reads results
bd show llm-dsl-xxx
bd show llm-dsl-yyy
bd show llm-dsl-zzz

# Main agent creates summary
bd create "Summary: Add validation" \
  --labels "agent=main,type=summary" \
  --body-file - <<'EOF'
[summary id=s1 s=ok]...[/summary]
EOF
```

## Why DSL All the Way?

1. **Structured** — machine-parseable, queryable
2. **Compact** — less token cost than NL
3. **Composable** — agents can reference each other's output
4. **Auditable** — full history of what each agent did
5. **No translation loss** — NL→DSL→NL round-trips lose information

The user reads DSL summaries. If they need NL, they can ask the main agent
to expand any summary item into prose.

# Validation Testcase: PoC Acceptance

## Scenario: "Add Input Validation to a REST API Endpoint"

A user asks the agent system to add input validation to an existing REST API endpoint. This is a realistic, common task that naturally decomposes into parallel and sequential subagent work.

### Starting State

A small Python/FastAPI project with an unvalidated endpoint:

```python
# src/handlers/user.py
@app.post("/users")
async def create_user(request: Request):
    body = await request.json()
    user = db.users.insert(body)
    return {"id": user.id}
```

### User Request (Natural Language)

```
"Add input validation to the POST /users endpoint. 
Validate that email is a valid format, name is required 
and at most 100 chars, and age is an optional int between 
0 and 150. Return proper 422 errors for invalid input."
```

### Agent Workflow

```
User ──NL──▶ Main Agent ──DSL──┬──▶ Subagent: Coder
                                ├──▶ Subagent: Reviewer  
                                └──▶ Subagent: Tester
                                
        Main Agent ◀──DSL──────┴── all results
        
User ◀──NL── Main Agent
```

**Step 1 — Main Agent** decomposes the request into three parallel tasks.

**Step 2 — Coder** writes the validation code, produces artifacts + DSL result.

**Step 3 — Reviewer** reviews the code for correctness, security, style. Reads coder's output via DSL reference (not re-sent). Produces DSL review result.

**Step 4 — Tester** writes and runs tests. Reads coder's output via DSL reference. Produces DSL test result.

**Step 5 — Main Agent** aggregates all DSL results → expands to NL for user.

---

## Expected Message Flow

### Message 1: Main Agent → Coder (DSL)

```dsl
[task id=t1 type=code]
  [goal]Add input validation to POST /users endpoint[/goal]
  [file read=src/handlers/user.py]
  [spec]
    [field name=email required=true rule=format:email]
    [field name=name required=true rule=length:max=100]
    [field name=age required=false type=int rule=range:0-150]
    [on-invalid status=422 format=standard-error]
  [/spec]
  [output-artifact path=src/handlers/user.py]
  [output-artifact path=src/validation/user_schema.py]
[/task]
```

### Message 2: Main Agent → Reviewer (DSL)

```dsl
[task id=t2 type=review]
  [goal]Review validation code for correctness, security, style[/goal]
  [context-ref id=t1.artifacts]
  [focus security=true style=true correctness=true]
  [schema-review]true[/schema-review]
[/task]
```

### Message 3: Main Agent → Tester (DSL)

```dsl
[task id=t3 type=test]
  [goal]Write and run tests for user input validation[/goal]
  [context-ref id=t1.artifacts]
  [test-cases]
    [case]valid email + name + age → 200[/case]
    [case]invalid email → 422[/case]
    [case]missing name → 422[/case]
    [case]=age 200 → 422[/case]
  [/test-cases]
  [output-artifact path=tests/test_user_validation.py]
[/task]
```

### Message 4: Coder → Main Agent (DSL)

```dsl
[result id=t1 status=complete]
  [artifact type=file path=src/handlers/user.py 
            action=modified lines=+23]
  [artifact type=file path=src/validation/user_schema.py 
            action=created lines=18]
  [added fn=validate_user_input in:RequestBody 
        out:ValidationResult]
  [test id=manual status=pass note="smoke tested locally"]
  [complexity delta=+2cyclomatic]
[/result]
```

### Message 5: Reviewer → Main Agent (DSL)

```dsl
[result id=t2 status=complete]
  [verdict approve]
  [finding severity=minor line=src/handlers/user.py:34]
    Email regex does not support international domains.
    Consider using a library like email-validator.
  [/finding]
  [security-check status=pass]
    [note]SQL injection not applicable — uses ORM[/note]
  [/security-check]
  [style status=pass]
[/result]
```

### Message 6: Tester → Main Agent (DSL)

```dsl
[result id=t3 status=complete]
  [artifact type=file path=tests/test_user_validation.py 
            action=created lines=45]
  [test-suite total=8 pass=7 fail=1]
    [test name=test_age_boundary_150 status=pass]
    [test name=test_age_boundary_neg1 status=pass]
    [test name=test_missing_name status=pass]
    [test name=test_invalid_email status=pass]
    [test name=test_valid_full_input status=pass]
    [test name=test_age_200 status=pass]
    [test name=test_age_boundary_0 status=pass]
    [test name=test_sql_injection_name status=fail
           reason="Input not sanitized — SQL chars pass through"]
  [/test-suite]
[/result]
```

### Message 7: Main Agent → User (Natural Language)

```
"All done. Here's what happened:

Code: Added validate_user_input() with field rules for 
email format, name length (max 100), and age range (0-150). 
Returns 422 with standard error format on invalid input.

Review: Approved with one minor note — the email regex 
doesn't support international domains. Consider switching 
to the email-validator library later.

Tests: 7 of 8 pass. One failure: SQL injection characters
in the name field pass through to the database. The reviewer
flagged that the ORM handles this, but you may want to add 
character-level sanitization on the name field for defense 
in depth.

Files changed: src/handlers/user.py (+23 lines), 
src/validation/user_schema.py (new), 
tests/test_user_validation.py (new)."
```

---

## Token Count Comparison

### NL Baseline (what agents send today)

Estimated token counts for equivalent information in natural language:

| Message | NL Tokens (est.) |
|---------|------------------|
| M1: Main → Coder | ~120 |
| M2: Main → Reviewer | ~60 |
| M3: Main → Tester | ~100 |
| M4: Coder → Main | ~80 |
| M5: Reviewer → Main | ~70 |
| M6: Tester → Main | ~90 |
| M7: Main → User | ~100 |
| **Total** | **~620** |

### DSL (compressed inter-agent) + NL (human boundary only)

| Message | Type | DSL Tokens (est.) | NL Tokens (est.) |
|---------|------|--------------------|-------------------|
| M1: Main → Coder | DSL | ~55 | — |
| M2: Main → Reviewer | DSL | ~30 | — |
| M3: Main → Tester | DSL | ~45 | — |
| M4: Coder → Main | DSL | ~40 | — |
| M5: Reviewer → Main | DSL | ~35 | — |
| M6: Tester → Main | DSL | ~40 | — |
| M7: Main → User | NL | — | ~100 |
| **Total** | | **~245** | **~100** |

**Estimated savings: ~520 tokens (84%) on inter-agent messages, ~63% overall.**

Note: These are rough estimates. Actual validation must use a real tokenizer (tiktoken for OpenAI, tokenizers for local models).

---

## What This Testcase Validates

| Design Area | Validated By |
|-------------|-------------|
| **Schema format** | Message structure, types, nesting, references |
| **Protocol** | Task dispatch, parallel execution, result collection, error handling (test failure in M6) |
| **Process definition** | Agent topology (1→3→1), typed subagents |
| **Schema drift** | Reviewer adds `security-check` field that coder doesn't know about — main agent must passthrough |
| **Bootstrapping** | Schema overhead per subagent system prompt — measurable |
| **Human output** | M7: main agent aggregates 7→1 NL summary with right level of detail |
| **Translator** | NL→DSL at input (user msg to task dispatch), DSL→NL at output (results to user summary) |

---

## Acceptance Criteria

1. **Round-trip fidelity**: Every DSL message must losslessly expand to the equivalent NL. No information lost.

2. **Token savings**: Measured token count for DSL messages must be ≤50% of equivalent NL messages (using tiktoken `cl100k_base`).

3. **Composability**: The reviewer and tester can reference `t1.artifacts` without the main agent re-sending file contents.

4. **Aggregation**: The main agent can combine results from all three subagents into a single coherent NL summary without any subagent needing to know about the others.

5. **Determinism**: For the same structured data, the DSL output must be identical (no reformatting on re-generation).

6. **Schema resilience**: If the reviewer emits a field not in the schema (e.g., `security-check`), the main agent preserves and relays it.

7. **Process declaration**: The entire topology (main + 3 subagents, message types, schemas) must be expressible in a single process definition file.

---

## Out of Scope for PoC

- Concurrent subagent execution (simulate sequential)
- Streaming/chunked responses
- Local model translation fallback (use static only)
- Schema versioning (v1 only)
- Dynamic agent spawning (fixed topology)
- Authentication or sandboxing

# Human Output Generation Design

## Problem

The main agent must aggregate all subagent DSL results into a single coherent NL summary for the user. Humans no longer read the raw code — they read the agent's summary. This output must be minimal but informative.

## Output Generation Pipeline

```
Subagent DSL results
       │
       ▼
┌──────────────┐
│ 1. COLLECT   │ Gather all [result] messages
└──────┬───────┘
       ▼
┌──────────────┐
│ 2. EXPAND    │ DSL → structured data (resolve refs, flatten)
└──────┬───────┘
       ▼
┌──────────────┐
│ 3. TEMPLATE  │ Select output template per agent type
└──────┬───────┘
       ▼
┌──────────────┐
│ 4. RENDER    │ Template + data → NL text
└──────┬───────┘
       ▼
┌──────────────┐
│ 5. AGGREGATE │ Combine per-agent NL into single summary
└──────┬───────┘
       ▼
  NL to user
```

## Verbosity Levels

| Level | When to use | What's included |
|-------|-------------|-----------------|
| `summary` | Default. Routine tasks, all green. | What changed, verdict, any issues |
| `detailed` | User asks for details, or something went wrong. | Full findings, test results, file changes |
| `debug` | User explicitly asks, or escalating failures. | Everything including DSL wire form |

For PoC: only `summary` level is implemented.

## Output Templates

Templates are defined per agent type. They are **not** part of the DSL — they're part of the main agent's system prompt (Layer 3).

### Coder Output Template

```
Code: {{summary of added/removed artifacts}}.
{{#if findings}}Note: {{findings}}{{/if}}
{{#if test_failures}}Tests: {{test_failures}}{{/if}}
Files: {{file_list}}.
```

Expanded example:
```
Code: Added validate_user_input() with field rules for email
format, name length (max 100), and age range (0-150). Returns
422 with standard error format on invalid input.
Files: src/handlers/user.py (+23 lines),
src/validation/user_schema.py (new).
```

### Reviewer Output Template

```
Review: {{verdict}}.
{{#if findings}}Findings: {{#each findings}}{{severity}}: {{text}}. {{/each}}{{/if}}
{{#if security}}Security: {{security.status}}. {{security.note}}{{/if}}
```

Expanded example:
```
Review: Approved with one minor note — the email regex
doesn't support international domains. Consider switching to
the email-validator library later.
Security: Pass — SQL injection not applicable, uses ORM.
```

### Tester Output Template

```
Tests: {{pass_count}}/{{total}} pass.
{{#if failures}}Failures: {{#each failures}}{{name}}: {{reason}}. {{/each}}{{/if}}
```

Expanded example:
```
Tests: 7 of 8 pass. One failure: SQL injection characters in
the name field pass through to the database.
```

## Aggregation Rules

The main agent combines per-agent outputs into a single summary:

1. **Order**: Coder → Reviewer → Tester (pipeline order)
2. **Deduplication**: If reviewer and tester both mention the same issue, mention it once with both attributions
3. **Conflict handling**: If reviewer approves but tests fail, present both — don't suppress either
4. **Action items**: End with any items needing user attention

### Aggregation Template

```
{{coder_output}}

{{reviewer_output}}

{{tester_output}}

{{#if action_items}}Needs attention: {{action_items}}{{/if}}
```

## DSL→NL Expansion Rules

The expansion from DSL to template data is **static** (no LLM needed):

| DSL construct | Expansion |
|---------------|-----------|
| `[artifact path=X a=mod n=+N]` | "X (+N lines)" |
| `[artifact path=X a=new]` | "X (new)" |
| `[added fn=F in:A out:B]` | "Added F(A) → B" |
| `[verdict approve]` | "Approved" |
| `[verdict request-changes]` | "Changes requested" |
| `[note sev=S at=P]text[/note]` | "S finding at P: text" |
| `[suite t=T p=P f=F]` | "P of T pass, F fail" |
| `[test name=N s=fail reason=R]` | "N failed: R" |
| `[security-check s=S]` | "Security: S" |
| Passthrough tags | Expanded as "Tag content: ..." |

## Design Decisions

- **Static expansion only for PoC**: No local model needed. Templates + rules cover the validation testcase.
- **Templates in system prompt Layer 3**: The main agent's Layer 3 includes the output templates. This is ~200 tokens.
- **No template per process**: Templates are per agent type (coder/reviewer/tester), reusable across processes.
- **Minimal by default**: The summary level intentionally omits detail. The user can ask for more.

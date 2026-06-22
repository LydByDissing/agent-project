# Static Translator Design

## Problem

Translation between DSL and NL should be static (no LLM) wherever possible. Local model is optional polish at human boundaries only.

## Translation Architecture

```
                    NL (user input)
                         │
                         ▼
              ┌─────────────────────┐
              │  NL → DSL           │
              │  (Main agent LLM)   │  ← LLM needed: understand intent
              └──────────┬──────────┘
                         │ DSL
                         ▼
              ┌─────────────────────┐
              │  Agent workflow     │
              │  (DSL in, DSL out)  │  ← No translation needed
              └──────────┬──────────┘
                         │ DSL
                         ▼
              ┌─────────────────────┐
              │  DSL → NL           │
              │  (Static rules)     │  ← No LLM needed
              └──────────┬──────────┘
                         │
                         ▼
                    NL (user output)
```

## NL → DSL Translation (Main Agent Input)

This **requires the main agent LLM**. Static rules cannot reliably parse arbitrary NL intent into structured DSL. The main agent:

1. Receives NL from user
2. Understands the intent
3. Constructs task messages in DSL using the schema

For the PoC, this is a standard LLM call with the system prompt including:
- The process definition (schemas, agents, composition)
- Instructions for constructing valid DSL

## DSL → NL Translation (Main Agent Output)

This is **static**. No LLM, no local model. Pure template + rule expansion.

### Approach

1. **Parse** the DSL into a structured data tree (tags, attributes, children, text).
2. **Expand** known tags using static rules:
   - `[artifact path=X a=mod n=+N]` → "X (+N lines, modified)"
   - `[verdict approve]` → "Approved"
   - `[suite t=T p=P f=F]` → "P of T tests pass"
3. **Passthrough** unknown tags with a generic expansion:
   - `[security-check s=pass]...[/security-check]` → "Security check: Pass. [content]"
4. **Fill** the output template (from `human-output.md`) with expanded data.

### Static Expansion Rules

| DSL Construct | NL Expansion |
|---------------|-------------|
| `[artifact path=P a=new n=N]` | "Created P (N lines)" |
| `[artifact path=P a=mod n=+N]` | "Modified P (+N lines)" |
| `[artifact path=P a=del]` | "Deleted P" |
| `[added fn=F]` | "Added F" |
| `[added fn=F in:A out:B]` | "Added F(A) → B" |
| `[removed fn=F]` | "Removed F" |
| `[verdict approve]` | "Approved" |
| `[verdict request-changes]` | "Changes requested" |
| `[verdict block]` | "Blocked" |
| `[note sev=S at=P]text[/note]` | "S finding at P: text" |
| `[suite t=T p=P f=F]` | "P of T tests pass, F fail" |
| `[test name=N s=fail reason=R]` | "N failed: R" |
| `[test name=N s=pass]` | (omitted in summary, counted only) |
| `[error code=C sev=S]` | "Error (C, S)" |
| Passthrough tag `[X]` | "X: [content]" |

### Template Filling

The NL output templates (from `human-output.md`) use simple placeholder substitution:

```
Template: "Code: {{coder.summary}}. Files: {{coder.files}}."
Data:     coder.summary = "Added validate_user_input()..."
          coder.files = ["src/handlers/user.py (+23)", "src/validation/user_schema.py (new)"]
Output:   "Code: Added validate_user_input()... Files: src/handlers/user.py (+23), src/validation/user_schema.py (new)."
```

For the PoC, template filling is simple string concatenation and join — no templating engine needed.

## Caching

Common expansions can be cached. The cache key is the DSL wire form of the tag. For example:

```
Input:  [artifact a=mod n=+23 path=src/handlers/user.py]
Cache:  "Modified src/handlers/user.py (+23 lines)"
```

For PoC: no caching needed. The expansion is fast enough.

## Fallback to Local Model

In the PoC, there is no local model fallback. If the static translator encounters a construct it cannot expand, it uses the generic passthrough format:

```
[unknown-tag attr=val]: raw-text-content
```

Future: A local model could be used to produce more natural NL from the structured data. This would be similar to the static expansion but with more fluent output.

## Translator Implementation

The translator is two simple functions:

```python
# DSL → structured data
def parse_dsl(wire_form: str) -> dict:
    """Parse DSL wire form into a dict tree."""
    ...

# Structured data → NL
def expand_to_nl(parsed: dict, agent_type: str, template: str) -> str:
    """Expand structured data into NL using static rules + template."""
    ...

# Convenience: wire form → NL
def dsl_to_nl(wire_form: str, agent_type: str) -> str:
    parsed = parse_dsl(wire_form)
    template = get_template(agent_type)
    return expand_to_nl(parsed, agent_type, template)
```

Both functions are pure, deterministic, and stateless. No LLM calls.

## Design Decisions

- **Static for output**: DSL→NL at the human boundary is static because the structure is known (schema-defined tags) and the templates are simple.
- **LLM for input**: NL→DSL requires intent understanding, which needs the main agent LLM.
- **No local model in PoC**: Static expansion + templates are sufficient. Reduces complexity and dependencies.
- **Passthrough for unknowns**: If the static translator encounters an unknown tag, it wraps it generically rather than failing.
- **Parser is simple**: The DSL grammar is simple enough for a recursive descent parser. No need for a grammar generator.

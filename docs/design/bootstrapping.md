# Bootstrapping & Schema Distribution Design

## Problem

Every subagent needs the schema in its system prompt. For small/simple tasks, this overhead might negate DSL token savings.

## System Prompt Construction

Each subagent's system prompt is built from three layers:

| Layer | Source | Contents | Token Cost |
|-------|--------|----------|------------|
| 1 — Core DSL | Auto-generated from `message-schema.md` | Syntax form, core tags, types, serialization rules, reference mechanism | ~400-500 tokens |
| 2 — Domain Schema | Auto-generated from process definition | Agent's input/output schema fields, enums, types | ~150-400 tokens |
| 3 — Agent Instructions | From `system-prompt` file in process def | Role description, task-specific guidance, output formatting | ~100-300 tokens |

Total per-agent system prompt: **~650-1200 tokens**.

## Minimizing Layer 1 (Core DSL)

The core DSL reference is the same for every agent. It is generated once and included via reference, not duplicated:

```
# In system prompt — instead of the full reference:
## DSL Reference
{{core-dsl-reference}}

# The harness resolves {{core-dsl-reference}} to the shared content.
# Counted once in the context window, shared across all agents.
```

In practice, for PoC where we have a single process, Layer 1 is included verbatim. The ~500 token cost is amortized across all agent invocations in the process.

## Minimizing Layer 2 (Domain Schema)

Layer 2 only includes the schemas the specific agent needs:

```
# Coder agent Layer 2 — only code-task (input) and code-result (output):
## Your Task Schema (input)
[task type=code] with fields: goal, spec, file
  spec children: field*, on-invalid
    field attrs: name, required, type, rule

## Your Result Schema (output)
[result] with fields: artifact*, added*, removed*, test*, complexity*
  artifact attrs: type, path, action, lines
  added attrs: fn, in, out
```

Not included: review-task, review-result, test-task, test-result. The coder doesn't need to know the reviewer's schema.

## Context Budget

Most agent models provide a 200k token context window. Realistically ~50% is usable before quality degradation:

```
Total context window:  200,000 tokens
Usable budget:         100,000 tokens
```

Budget allocation within the usable 100k:

```
System prompt (shared):   ~2,000 tokens
  Layer 1 (core DSL):       ~150 tokens  (compact cheat sheet)
  Layer 2 (schemas):        ~400 tokens  (sum across all agent types)
  Layer 3 (instructions):   ~300 tokens  (main agent orchestration)
  Layer 3 (per subagent):   ~300 tokens  x N agents (not in main agent ctx)

User message:             ~500 tokens
Tool definitions:          ~5,000 tokens (if using tool-calling agent)
---
Fixed overhead:           ~7,500 tokens
Remaining for messages:   ~92,500 tokens
```

This is a massive budget. The DSL does not need to fight for space -- it needs to keep messages small enough that complex multi-step workflows (dozens of agent hops, iterative loops, accumulated context) stay well within bounds.

## Token Savings Analysis

The real value is not fitting more messages -- it is **reducing token cost per message** so that:
1. Iterative loops (review, fix, re-review, re-test) do not accumulate cost linearly
2. Re-sending file contents and context is avoided via context-ref
3. The main agent synthesis step has less noise to filter through

### Savings (per message)
- Average NL message: ~80 tokens
- Average DSL message: ~40 tokens
- Savings per message: ~40 tokens

With the validation testcase (6 DSL messages):
- DSL total: ~245 tokens (M1-M6) + ~100 tokens (M7 NL) = ~345 tokens
- NL equivalent: ~620 tokens
- Savings: ~275 tokens (44%) on this small workflow

The savings compound on larger workflows. A 10-hop iterative review cycle:
- NL: ~800 tokens x 10 = ~8,000 tokens
- DSL: ~400 tokens x 10 = ~4,000 tokens
- Savings: ~4,000 tokens per iteration cycle

## Schema Caching

For PoC: no caching. Schema is included in every invocation.

Future: If the same process runs repeatedly, the schema layers can be cached in the agent's persistent context and not re-sent. Only Layer 3 and the actual task/result messages are sent per invocation.

Design Decision

The ~500 token Layer 1 overhead is the biggest concern. Solution: keep it compact. The core reference should be a terse summary, not verbose documentation. Think "cheat sheet" not "specification."

Example compact form:

```
## DSL SYNTAX: [tag k=v]content[/tag]
## ATTERS: sorted alpha, bare k=v
## TYPES: str int bool path(id:line)
## CORE: task(id,type) result(id,status) artifact(type,path,action)
        context-ref(id=ref.tag) file(path) added(fn) removed(fn)
## REFERENCE: ref=<msgid>.<field> — resolvable only if msg already delivered
## SERIALIZE: single-line, no indentation, no pretty-print
```

That's ~150 tokens instead of 500. Break-even drops to ~25 messages for 3 agents.

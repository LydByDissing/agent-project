# Agent Process Definition Format Design

## Goals

- Declaratively define the entire agent topology in one file
- Associate agents with their input/output schemas and system prompts
- Support composition: pipeline, parallel, loop, conditional
- Machine-parseable and human-readable
- Sufficient to generate subagent system prompts and validate message flow

## Non-Goals

- Runtime agent spawning / dynamic topologies (PoC: fixed topology only)
- Schema versioning (v1 only)
- Resource limits, sandboxing, authentication

---

## 1. File Structure

A process definition is a YAML file. For the PoC, a single file defines one process:

```yaml
# process.yaml
process: <process-name>
version: "1.0"

schemas:
  # Schema definitions (shared DSL vocabulary)
  ...

agents:
  # Agent declarations with roles and schema bindings
  ...

topology:
  # Communication graph and dispatch rules
  ...

composition:
  # Process-level flow definition
  ...
```

---

## 2. Schema Definitions

### 2.1 Schema Block

The `schemas` block defines the DSL vocabulary available in this process. It merges with the core schema (always available).

```yaml
schemas:
  <schema-name>:
    extends: <base schema or "core">
    fields:
      <field-name>: <type>
    enums:
      <enum-name>: [<value>, ...]
    description: <human-readable explanation>
```

### 2.2 Schema for the Validation Testcase

```yaml
schemas:
  code-task:
    extends: core
    description: "Task dispatched to the Coder subagent"
    fields:
      spec:
        type: structured
        children:
          field:
            type: repeated
            attrs: {name: str, required: bool, type: str, rule: str}
          on-invalid:
            type: structured
            attrs: {status: int, str}
      output-artifact:
        type: repeated
        attrs: {path: path}
    enums:
      task-type: [code]

  review-task:
    extends: core
    description: "Task dispatched to the Reviewer subagent"
    fields:
      focus:
        type: structured
        attrs: {security: bool, style: bool, correctness: bool}
      context-ref:
        type: reference
    enums:
      task-type: [review]

  review-result:
    extends: core
    description: "Result received from the Reviewer subagent"
    fields:
      verdict:
        type: enum
        values: [approve, request-changes, block]
      finding:
        type: repeated
        attrs: {severity: enum, path: path}
        severity values: [critical, major, minor, info]
      security-check:
        type: opaque  # schema drift: preserved but not validated
        status: enum
        status values: [pass, fail, warn]
        children:
          note: {type: text}
      style:
        type: status-only
        values: [pass, fail, warn]

  test-task:
    extends: core
    description: "Task dispatched to the Tester subagent"
    fields:
      test-cases:
        type: list-of-text
      output-artifact:
        type: repeated
        attrs: {path: path}
    enums:
      task-type: [test]

  test-result:
    extends: core
    description: "Result received from the Tester subagent"
    fields:
      test-suite:
        type: structured
        attrs: {total: int, pass: int, fail: int}
        children:
          test:
            type: repeated
            attrs: {name: str, status: enum, reason: str}
            status values: [pass, fail, skip, error]
```

### 2.3 Schema Types Reference

Schema fields use these type annotations:

| Type | YAML syntax | DSL equivalent |
|------|-------------|----------------|
| `str` | `type: str` | bare text |
| `int` | `type: int` | integer |
| `bool` | `type: bool` | `true`/`false` |
| `path` | `type: path` | `foo/bar.py:42` |
| `id` | `type: id` | `task-42` |
| `enum` | `type: enum` + `values: [...]` | bare keyword |
| `text` | `type: text` | `[tag]text[/tag]` |
| `structured` | `type: structured` | `[tag attrs...]...[/tag]` |
| `repeated` | `type: repeated` | repeated `[tag]...[/tag]` |
| `reference` | `type: reference` | `[context-ref id=ref]` |
| `list-of-text` | `type: list-of-text` | `[list][item]...[/item][/list]` |
| `opaque` | `type: opaque` | unknown fields — preserved, not validated |
| `status-only` | `type: status-only` + values | `[tag status=val]` (no body) |

The `opaque` type is the schema drift mechanism — it declares that a field exists but its contents are not validated. The passthrough mechanism (per `message-schema.md`) preserves it as-is.

---

## 3. Agent Declarations

### 3.1 Agent Block

Each agent declares its role, system prompt, model config, and schema bindings.

```yaml
agents:
  <agent-id>:
    role: <role-type>
    label: <human-readable name>
    description: <what this agent does>
    system-prompt: <inline string or path to file>
    model: <model-id or "inherit">
    schema:
      input: <schema-name or list>
      output: <schema-name or list>
    validation: <strict|permissive|open>
    max-retries: <int>
    context-budget: <int, tokens>
```

### 3.2 Role Types

| Role | Description | NL access |
|------|-------------|-----------|
| `orchestrator` | Main agent. Talks to user, dispatches tasks, aggregates results. | Read + Write |
| `worker` | Subagent. Receives tasks, produces results. Never talks to user. | None |

Exactly **one** agent in a process must have `role: orchestrator`. All others are `worker`.

### 3.3 System Prompt Management

The system prompt for each agent is constructed from three layers:

```
┌─────────────────────────────────────────┐
│  Layer 1: Core DSL reference             │  (auto-generated from core schema)
│  - DSL syntax form                       │
│  - Core tags (task, result, artifact...) │
│  - Type system                           │
│  - Serialization rules                   │
│  - Reference mechanism                   │
├─────────────────────────────────────────┤
│  Layer 2: Domain schema reference        │  (auto-generated from declared schemas)
│  - Agent-specific input/output schemas   │
│  - Field types and enums                 │
└─────────────────────────────────────────┘
│  Layer 3: Agent-specific instructions    │  (from system-prompt field)
│  - Role description                      │
│  - Task-specific guidance                │
│  - Output formatting rules               │
└─────────────────────────────────────────┘
```

Layers 1 and 2 are **generated** from schema definitions. Layer 3 is provided by the process author.

This separation minimizes the token cost of Layer 3 (the agent-specific part) while keeping Layers 1 and 2 consistent and correct.

### 3.4 Validation at the Agent Level

Each agent declares its validation strictness:

```yaml
agents:
  coder:
    validation: permissive    # default — preserves unknown fields
  reviewer:
    validation: permissive
  tester:
    validation: strict        # reject messages with unknown fields
```

See `message-schema.md` §7 for validation mode definitions.

### 3.5 Agent Declarations for Validation Testcase

```yaml
agents:
  main:
    role: orchestrator
    label: "Main Orchestrator"
    description: >
      Orchestrates code changes by dispatching tasks to 
      subagents and aggregating results for the user.
    system-prompt: prompts/main.md
    model: inherit    # use default/model from runtime config
    schema:
      input: [code-task, review-task, test-task]
      output: [code-result, review-result, test-result]
    validation: permissive
    max-retries: 3
    context-budget: 4500

  coder:
    role: worker
    label: "Coder"
    description: "Implements code changes based on specifications."
    system-prompt: prompts/coder.md
    schema:
      input: code-task
      output: code-result
    validation: permissive
    max-retries: 3
    context-budget: 3000

  reviewer:
    role: worker
    label: "Code Reviewer"
    description: "Reviews code for correctness, security, and style."
    system-prompt: prompts/reviewer.md
    schema:
      input: review-task
      output: review-result
    validation: permissive
    max-retries: 2
    context-budget: 3000

  tester:
    role: worker
    label: "Tester"
    description: "Writes and runs tests for code changes."
    system-prompt: prompts/tester.md
    schema:
      input: test-task
      output: test-result
    validation: permissive
    max-retries: 2
    context-budget: 3000
```

---

## 4. Topology Definition

### 4.1 Topology Block

The topology block defines who can send what to whom.

```yaml
topology:
  routes:
    - from: <agent-id>
      to: <agent-id>
      messages: [<message-type>, ...]
    # ...
  # Constraints (optional, for validation)
  constraints:
    - <constraint-expression>
```

### 4.2 Topology for Validation Testcase

```yaml
topology:
  routes:
    - from: main
      to: coder
      messages: [task, cancel]
    - from: main
      to: reviewer
      messages: [task, cancel]
    - from: main
      to: tester
      messages: [task, cancel]
    - from: coder
      to: main
      messages: [result, ask, error]
    - from: reviewer
      to: main
      messages: [result, ask, error]
    - from: tester
      to: main
      messages: [result, ask, error]

  constraints:
    - "main is the only orchestrator"
    - "workers cannot route to each other"
    - "all worker results route to main"
```

### 4.3 Route Validation

At parse time, the process definition is validated:
1. All `from`/`to` agents must be declared.
2. All message types must be valid (core or domain-declared).
3. Orchestrator must be able to send `task` and receive `result` for every worker.
4. No worker-to-worker routes (PoC constraint).

---

## 5. Composition Primitives

The `composition` block defines the **flow pattern** — how tasks are dispatched and results collected. This is the process-level control flow.

### 5.1 Primitives Overview

| Primitive | Description | DSL construct |
|-----------|-------------|---------------|
| `pipeline` | Sequential steps, each depends on prior | implicit via context-ref |
| `parallel` | Fan-out to N agents, wait for all | batch-id grouping |
| `loop` | Repeat a step until condition met | iteration in composition |
| `conditional` | Dispatch based on result evaluation | if/else in composition |

### 5.2 Composition Block

```yaml
composition:
  pattern: <pipeline|parallel|conditional|loop>
  steps:
    - id: <step-id>
      agent: <agent-id>
      task: <schema-name>
      on-finish: <step-id|"end"|"loop">
      on-fail: <step-id|"abort"|"skip">
    # ... (plus pattern-specific fields)
```

### 5.3 Pipeline (Sequential)

Steps execute in order. Each step's output is available as context for the next.

```yaml
composition:
  pattern: pipeline
  steps:
    - id: implement
      agent: coder
      task: code-task
      on-finish: review
      on-fail: abort
    - id: review
      agent: reviewer
      task: review-task
      context-from: implement   # auto-inject context-ref to prior step
      on-finish: end
      on-fail: implement        # re-implement on review failure
```

### 5.4 Parallel (Fan-Out)

All steps execute simultaneously. Results are aggregated when all complete.

```yaml
composition:
  pattern: parallel
  batch-id: validation-suite
  steps:
    - id: review
      agent: reviewer
      task: review-task
      context-from: implement   # both reference the same prior step
    - id: test
      agent: tester
      task: test-task
      context-from: implement
```

### 5.5 Conditional

Dispatch based on evaluation of a result field. The main agent evaluates the condition (not expressed in DSL).

```yaml
composition:
  pattern: conditional
  steps:
    - id: implement
      agent: coder
      task: code-task
      on-finish: check-review
      on-fail: abort
    - id: check-review      # virtual step — main agent evaluates
      evaluate: "review.result.verdict"
      branches:
        approve: end
        request-changes: implement   # loop back
        block: abort
```

### 5.6 Loop (Iteration)

Repeat a step (or pipeline) until a condition is met or max iterations reached.

```yaml
composition:
  pattern: loop
  max-iterations: 3
  steps:
    - id: implement
      agent: coder
      task: code-task
      on-finish: check
      on-fail: abort
    - id: check
      evaluate: "result.status"
      branches:
        complete: end
        partial: implement    # iterate with prior context
        failed: abort
```

### 5.7 Composition for Validation Testcase

The validation testcase uses a **pipeline into parallel** pattern:

```
Step 1: Coder (code-task)         — pipeline step
Step 2: Parallel review + test     — both reference Step 1's result
```

This is expressed as:

```yaml
composition:
  pattern: pipeline
  steps:
    - id: implement
      agent: coder
      task: code-task
      on-finish: validate
      on-fail: abort

    - id: validate
      pattern: parallel       # nested composition
      batch-id: validation
      steps:
        - id: review
          agent: reviewer
          task: review-task
          context-from: implement
          on-finish: aggregate
          on-fail: aggregate   # still aggregate (partial ok)
        - id: test
          agent: tester
          task: test-task
          context-from: implement
          on-finish: aggregate
          on-fail: aggregate

    - id: aggregate           # virtual step — main agent synthesizes
      pattern: aggregate
      sources: [validate.review, validate.test]
      on-finish: end
      on-fail: abort
```

### 5.8 Nested Composition

Composition primitives can be nested: a step in a pipeline can itself be a parallel block. This lets you express any DAG:

```
pipeline(
  step1,
  parallel(
    step2a,
    step2b
  ),
  step3    # runs after both 2a and 2b complete
)
```

Nesting depth is unlimited in the format, but for the PoC, max depth of 2 is recommended.

---

## 6. Complete Process Definition (Validation Testcase)

The entire validation testcase expressed as one process definition:

```yaml
# process.yaml — Add Input Validation pipeline
process: add-input-validation
version: "1.0"

schemas:
  code-task:
    extends: core
    description: "Coder task schema"
    fields:
      spec:
        type: structured
        children:
          field:
            type: repeated
            attrs: {name: str, required: bool, type: str, rule: str}
      output-artifact:
        type: repeated
        attrs: {path: path}

  review-task:
    extends: core
    description: "Reviewer task schema"
    fields:
      focus:
        type: structured
        attrs: {security: bool, style: bool, correctness: bool}
      context-ref:
        type: reference

  review-result:
    extends: core
    description: "Reviewer result schema"
    fields:
      verdict:
        type: enum
        values: [approve, request-changes, block]
      finding:
        type: repeated
        attrs: {severity: enum, path: path}
        severity: {values: [critical, major, minor, info]}
      security-check:
        type: opaque   # schema drift passthrough
      style:
        type: enum
        values: [pass, fail, warn]

  test-task:
    extends: core
    description: "Tester task schema"
    fields:
      test-cases:
        type: list-of-text
      output-artifact:
        type: repeated
        attrs: {path: path}

  test-result:
    extends: core
    description: "Tester result schema"
    fields:
      test-suite:
        type: structured
        attrs: {total: int, pass: int, fail: int}
        children:
          test:
            type: repeated
            attrs: {name: str, status: enum, reason: str}
            status: {values: [pass, fail, skip, error]}

agents:
  main:
    role: orchestrator
    label: "Main Orchestrator"
    description: "Orchestrates code changes and aggregates results."
    system-prompt: prompts/main.md
    schema:
      input: [code-task, review-task, test-task]
      output: [code-result, review-result, test-result]
    validation: permissive
    max-retries: 3
    context-budget: 4500

  coder:
    role: worker
    label: "Coder"
    description: "Implements code changes from specifications."
    system-prompt: prompts/coder.md
    schema:
      input: code-task
      output: code-result
    validation: permissive
    max-retries: 3
    context-budget: 3000

  reviewer:
    role: worker
    label: "Code Reviewer"
    description: "Reviews code for correctness, security, and style."
    system-prompt: prompts/reviewer.md
    schema:
      input: review-task
      output: review-result
    validation: permissive
    max-retries: 2
    context-budget: 3000

  tester:
    role: worker
    label: "Tester"
    description: "Writes and runs tests for code changes."
    system-prompt: prompts/tester.md
    schema:
      input: test-task
      output: test-result
    validation: permissive
    max-retries: 2
    context-budget: 3000

topology:
  routes:
    - from: main
      to: [coder, reviewer, tester]
      messages: [task, cancel]
    - from: [coder, reviewer, tester]
      to: main
      messages: [result, ask, error]
  constraints:
    - "main is the only orchestrator"
    - "workers cannot route to each other"

composition:
  pattern: pipeline
  steps:
    - id: implement
      agent: coder
      task: code-task
      on-finish: validate
      on-fail: abort

    - id: validate
      pattern: parallel
      batch-id: validation
      steps:
        - id: review
          agent: reviewer
          task: review-task
          context-from: implement
          on-finish: aggregate
          on-fail: aggregate
        - id: test
          agent: tester
          task: test-task
          context-from: implement
          on-finish: aggregate
          on-fail: aggregate

    - id: aggregate
      pattern: aggregate
      sources: [validate.review, validate.test]
      on-finish: end
      on-fail: abort
```

---

## 7. Schema Registry

### 7.1 Registry Structure

Schemas can be defined inline (as above) or referenced from external files:

```yaml
schemas:
  code-task:
    $ref: "schemas/code-task.yaml"
```

For the PoC, all schemas are defined inline in the process file. External references are for future use.

### 7.2 Schema Resolution at Runtime

1. Load process definition YAML.
2. Merge all schema blocks into a single schema registry.
3. Generate system prompt Layers 1+2 from the registry.
4. Load Layer 3 from the `system-prompt` file path.
5. Combine and inject into each agent's system prompt at startup.

### 7.3 Schema Bundles (Future)

For reuse across processes, schemas can be packaged as bundles:

```yaml
# schemas/code-bundle.yaml
$schema: "llm-dsl-schema/v1"
schemas:
  code-task: ...
  review-task: ...
  test-task: ...

# process.yaml
schemas:
  $include: "schemas/code-bundle.yaml"
```

Not implemented in PoC.

---

## 8. Process Execution Lifecycle

When a process is executed:

```
1. LOAD
   ├── Parse process.yaml
   ├── Validate schema definitions
   ├── Validate topology (all routes valid)
   ├── Validate composition (no cycles, all refs resolve)
   └── Build schema registry

2. INITIALIZE
   ├── For each agent:
   │   ├── Generate Layers 1+2 (core + domain schemas)
   │   ├── Load Layer 3 (system-prompt file)
   │   ├── Combine into full system prompt
   │   └── Token-count the prompt (validate < context-budget)
   └── Initialize message store (empty)

3. EXECUTE
   ├── Main agent receives user NL input
   ├── Main agent enters composition-defined flow
   ├── For each step in composition:
   │   ├── Main agent constructs [task] from schema
   │   ├── Dispatch to subagent (or sequential simulation)
   │   ├── Await [result]
   │   ├── Store result in message store (idempotent)
   │   ├── Check context budget → summarize if needed
   │   └── Evaluate on-finish / on-fail
   └── When flow reaches "end": aggregate → NL → user

4. FINALIZE
   ├── Write message log (all DSL messages in order)
   ├── Write token usage report
   └── Clean up subagent contexts
```

---

## 9. Design Decisions & Rationale

### Why YAML for process defs?

- Human-readable and writable (unlike JSON)
- Good tooling support (validators, IDEs)
- Native multi-line strings for prompts
- References/anchors for deduplication

### Why separate schema from agent?

Schemas are the shared vocabulary. Multiple agents can reference the same schema. This avoids duplicating schema definitions across agent declarations and ensures consistency.

### Why three-layer system prompts?

Token economy. Layer 1 (core DSL) is ~500 tokens but changes rarely. Layer 2 (domain schemas) is ~200-500 tokens per agent type. Layer 3 (agent-specific) is the only part that's truly custom. By generating Layers 1-2 from the process definition, we ensure they're always correct and consistent, and the process author only writes Layer 3.

### Why nested composition instead of a flat step list?

Multi-agent workflows are DAGs, not flat sequences. Nested composition (pipeline containing parallel) is the minimal construct that can express any DAG. Flat lists with `depends-on` attributes are an alternative but harder to read and validate.

### Why `context-from` instead of explicit context-ref?

In the composition definition, `context-from: implement` tells the dispatcher to automatically inject a `context-ref` pointing to the referenced step's result. This is syntactic sugar — the actual DSL message still contains an explicit `[context-ref id=...]` tag with the resolved message ID. But the process author doesn't need to manually wire the references.

### Why virtual steps for aggregation and evaluation?

`aggregate` and `evaluate` steps are not agents — they're actions the main agent performs itself. By expressing them in the composition, the flow is explicit and complete, even though no subagent is involved.

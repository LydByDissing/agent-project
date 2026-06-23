# Communication Protocol Design

## Goals

- Define the complete lifecycle of a multi-agent task
- Handle parallel and sequential subagent execution
- Structured error propagation with clear retry/escalate decisions
- Manage context window growth as messages accumulate
- Deterministic behavior for the same inputs

---

## 1. Agent Roles and Communication Topology

### 1.1 Roles

| Role | Responsibility | NL? | DSL? |
|------|---------------|-----|------|
| **Main Agent** (orchestrator) | Talks to user, decomposes tasks, dispatches to subagents, aggregates results | Read+Read | Read+Write |
| **Subagent** (typed worker) | Receives task, does work, produces result + artifacts | No | Read+Write |

The main agent is the **only NL boundary**. All inter-agent communication is DSL.

### 1.2 Topology Rules

1. Subagents **never** communicate directly with each other.
2. Subagents **never** talk to the user.
3. The main agent is the sole router: all subagent results go to the main agent.
4. Subagents can **reference** prior messages via `context-ref` but cannot send messages to each other.

```
         ┌──────────────────┐
         │   User (NL)      │
         └───────┬──────────┘
                 │ NL
         ┌───────▼──────────┐
         │   Main Agent     │
         │   (orchestrator) │
         └───┬───┬───┬──────┘
             │   │   │ DSL
     ┌───────┘   │   └───────┐
     ▼           ▼           ▼
┌─────────┐┌─────────┐┌─────────┐
│Subagent ││Subagent ││Subagent │
│  Coder  ││ Reviewer││  Tester │
└─────────┘└─────────┘└─────────┘
```

---

## 2. Protocol State Machine

### 2.1 Process-Level State

A **process** is one complete user request → user response cycle.

```
                    ┌──────────┐
          ┌────────▶│ RECEIVING│ (user NL input)
          │         └────┬─────┘
          │              │ decompose
          │         ┌────▼─────┐
          │         │DISPATCHING│ (sending tasks to subagents)
          │         └────┬─────┘
          │              │ all tasks dispatched
          │         ┌────▼─────┐
          │         │AWAITING  │ (collecting results)
          │         └────┬─────┘
          │              │ all results received
          │         ┌────▼─────┐
          │         │AGGREGATING│ (combining results → NL)
          │         └────┬─────┘
          │              │ NL summary ready
          │         ┌────▼─────┐
          │         │COMPLETE  │ (NL to user)
          │         └──────────┘
          │
    retry / escalate
          │
          └──────────────┘
         
    (from any state)
          │
     ┌────▼─────┐
     │ FAILED   │ (unrecoverable error → NL error to user)
     └──────────┘
```

### 2.2 Task-Level State

Each individual task follows its own lifecycle:

```
┌──────────┐
│ CREATED  │ ← main agent constructs task
└────┬─────┘
     │ dispatch
┌────▼─────┐
│ DISPATCHED│ ← sent to subagent
└────┬─────┘
     │ subagent begins work
┌────▼─────┐
│ IN_PROGRESS│ (for long-running tasks, subagent can send progress)
└────┬─────┘
     │ subagent finishes
┌────▼──────┐
│ COMPLETED  │ ← result received
└───────────┘

     (alt paths)
     
┌────▼─────┐
│  FAILED   │ ← subagent reports failure
└────┬─────┘
     │ retry decision
┌────▼─────┐
│ RETRYING  │ ← re-dispatch same task (max retries)
└────┬─────┘
     │ max retries exceeded
┌────▼──────┐
│ ESCALATED  │ ← main agent decides: ask user / skip / abort
└───────────┘
```

---

## 3. Message Types and Flow

### 3.1 Main Agent → Subagent Messages

The main agent sends these message types:

| Message | Direction | Trigger |
|---------|-----------|---------|
| `[task]` | Main → Subagent | Work assignment |
| `[cancel]` | Main → Subagent | Cancel in-flight task |
| `[reassign]` | Main → Subagent | Reassign to different agent type |

### 3.2 Subagent → Main Agent Messages

Subagents send these message types:

| Message | Direction | Trigger |
|---------|-----------|---------|
| `[result]` | Subagent → Main | Task completion (any status) |
| `[ask]` | Subagent → Main | Need clarification to proceed |
| `[progress]` | Subagent → Main | Long-running task heartbeat (optional in PoC) |

### 3.3 New Message Types for Protocol

These are additions to the core schema defined in `message-schema.md`:

#### `[cancel]` — Cancel an in-flight task

```
[cancel id=<task-id> reason=<enum>]
```

**Attributes:**
| Attr | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `id` | yes | Task to cancel |
| `reason` | `enum` | yes | `user-request`, `dependency-failed`, `timeout`, `redundant` |

#### `[ask]` — Subagent needs clarification

```
[ask id=<task-id> question=<str>]
  [context]<what the subagent tried/needs[/context]
[/ask]
```

**Attributes:**
| Attr | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `id` | yes | Task this relates to |

The main agent either:
- Responds with an `[answer]` message containing the clarification
- Translates the question to NL and asks the user
- Decides the task can proceed without clarification and sends `[proceed]`

#### `[error]` — Structured error reporting

```
[error id=<task-id> code=<enum> sev=<enum>]
  [detail]<machine-readable error detail[/detail]
  [recovery]<suggested recovery action[/recovery]
[/error]
```

**Attributes:**
| Attr | Type | Required | Description |
|------|------|----------|-------------|
| `id` | `id` | yes | Task this relates to |
| `code` | `enum` | yes | Error code (see §5) |
| `sev` | `enum` | yes | `transient`, `permanent`, `unknown` |

---

## 4. Dispatch Patterns

### 4.1 Fan-Out (Parallel Dispatch)

The main agent dispatches multiple tasks simultaneously. All subagents work independently.

```
Main Agent
    ├──[task id=t1 type=code]──────────────▶ Coder
    ├──[task id=t2 type=review]────────────▶ Reviewer
    └──[task id=t3 type=test]─────────────▶ Tester
    
    ├──◀──[result id=t1 s=ok]──── Coder
    ├──◀──[result id=t2 s=ok]──── Reviewer
    └──◀──[result id=t3 s=ok]──── Tester
```

Rules:
- All tasks in a fan-out share a **batch id** for tracking.
- The main agent waits for **all** results before proceeding.
- If any task fails, the main agent decides per-task (retry/escalate/skip).

### 4.2 Pipeline (Sequential Dispatch)

Tasks are dispatched one after another. Each subsequent task depends on the previous result.

```
Main Agent ──[task id=t1]──▶ Coder
Main Agent ◀──[result id=t1]── Coder
Main Agent ──[task id=t2 context-ref=t1]──▶ Reviewer
Main Agent ◀──[result id=t2]── Reviewer
Main Agent ──[task id=t3 context-ref=t1,t2]──▶ Tester
Main Agent ◀──[result id=t3]── Tester
```

Rules:
- Each task includes a `context-ref` to the prior task's result.
- If any step fails, the pipeline halts and the main agent escalates.
- The main agent can insert conditional logic between steps.

### 4.3 Fan-Out + Fan-In (Parallel with Aggregation)

The main agent dispatches parallel tasks to different agent types, then aggregates results. **This is the primary pattern in the validation testcase.**

```
                  ┌──▶ Coder ──┐
Main Agent ───────┤            ├──▶ Main Agent → Aggregate → NL
                  ├──▶ Reviewer─┤
                  └──▶ Tester ──┘
```

Rules:
- Reviewer and Tester both reference Coder's result via `context-ref`.
- Main agent waits for all, then aggregates.
- Partial results are acceptable (one subagent can fail without failing the whole batch).

### 4.4 Conditional Dispatch

The main agent dispatches a follow-up task **only if** a condition is met.

```
Main Agent ──[task id=t1]──▶ Coder
Main Agent ◀──[result id=t1 verdict=request-changes]── Coder

# Condition: verdict != approve → dispatch fix
Main Agent ──[task id=t1.1 context-ref=t1]──▶ Coder
  [goal]Address review findings from t1[/goal]
  [context-ref id=t1.findings]
[/task]
```

In the PoC, conditions are evaluated by the main agent (not expressed in DSL). The DSL only expresses what to dispatch, not when.

---

## 5. Error Handling Taxonomy

### 5.1 Error Codes

| Code | Meaning | Typical Severity | Default Action |
|------|---------|-------------------|----------------|
| `schema-validation` | DSL message fails schema validation | permanent | escalate |
| `reference-stale` | `context-ref` points to non-existent message | transient | retry |
| `reference-partial` | `context-ref` resolves but field missing | transient | retry with full context |
| `tool-failure` | Subagent's tool call failed (e.g., file write error) | transient | retry |
| `context-overflow` | Subagent's context window exceeded | transient | retry with reduced context |
| `ambiguous-task` | Subagent cannot understand the task | permanent | escalate to user |
| `partial-output` | Subagent produced incomplete output | transient | re-ask with clarification |
| `timeout` | Subagent did not respond in time | transient | retry or reassign |
| `agent-crash` | Subagent crashed mid-task | transient | retry |

### 5.2 Retry Policy

```
max_retries = 3
backoff = [1x, 2x, 4x]  # multiplicative backoff on retries
```

Retry behavior:
1. **First retry**: re-dispatch same task to same agent type with full context.
2. **Second retry**: re-dispatch with additional context and narrower scope.
3. **Third retry**: escalate — ask user for guidance or skip the task.

The retry policy is **not** expressed in the DSL. It's a protocol-level concern managed by the main agent / harness.

### 5.3 Error Propagation Rules

1. A `[result s=fail]` is **not** an error — it's a valid result. The main agent reads the error details and decides.
2. An `[error]` message is for **infrastructure-level** failures (the subagent could not even produce a result).
3. The main agent **never** propagates raw error details to the user. It translates errors into NL.

```
# Internal (DSL):
[error code=tool-failure sev=transient]
  [detail]File write permission denied: /src/handler.py[/detail]
  [recovery]Retry with elevated permissions[/recovery]
[/error]

# User-facing (NL):
"Couldn't write to the handler file due to a permission 
issue. Trying again with different settings..."
```

---

## 6. Context Window Management

### 6.1 The Problem

As messages accumulate in a process, the main agent's context window fills up:
- Original user message
- All dispatched tasks (M1, M2, M3)
- All received results (M4, M5, M6)
- Intermediate reasoning / synthesis

Even with DSL compression, large workflows can overflow.

### 6.2 Strategies (in priority order)

#### Strategy 1: Reference, don't repeat

Already solved by the `context-ref` mechanism. Subagents reference prior results instead of re-sending data.

#### Strategy 2: DSL→DSL compression (summarization)

When the main agent's context approaches a threshold, it summarizes prior DSL messages into compact summaries:

```
# Original result (detailed):
[result id=t1 s=ok]
  [artifact a=mod n=+23 path=src/handlers/user.py]
  [artifact a=new n=18 path=src/validation/user_schema.py]
  [added fn=validate_user_input in:RequestBody out:ValidationResult]
  [test id=manual s=pass]
  [complexity delta=+2cyclomatic]
[/result]

# Compressed summary (for context retention):
[summary refs=t1]
  code: +2 files, +41 lines, verify_input() added
  review: approved, 1 minor
  tests: 7/8 pass, 1 fail (sql-injection)
[/summary]
```

The `[summary]` tag is a **lossy but sufficient** representation. It preserves the key facts needed for NL generation without the full detail.

#### Strategy 3: Artifact offloading

File artifacts are stored on disk, not in context. Only metadata (path, action, lines) stays in context. The main agent reads file contents only when needed for aggregation.

#### Strategy 4: Window sliding

For very long processes, the main agent drops messages that are no longer relevant to the current synthesis (messages that have been fully consumed and summarized).

### 6.3 Context Budget (PoC)

For the PoC, we set a conservative context budget:

| Component | Budget |
|-----------|--------|
| System prompt + schema | ~2000 tokens |
| User message | ~500 tokens |
| Tool definitions | ~5000 tokens |
| Dispatched tasks + received results | ~50000 tokens |
| Working space / synthesis | ~10000 tokens |
| **Total budget** | **~100,000 tokens** |

With a 200k context window and ~50% usable budget, the
summarization strategy only kicks in for very long-running
workflows (10+ iterative cycles). For the PoC validation
testcase (6 messages), no summarization is needed.

---

## 7. Complete Protocol Walkthrough (Validation Testcase)

```
STATE: RECEIVING
├── Main agent receives user NL request
├── Main agent parses intent: "add input validation"
├── Main agent decomposes into 3 tasks: t1=code, t2=review, t3=test
│
STATE: DISPATCHING
├── Send [task id=t1 type=code]        → Coder       (M1)
├── Send [task id=t2 type=review]      → Reviewer    (M2)
├── Send [task id=t3 type=test]        → Tester      (M3)
│   Note: t2 and t3 include context-ref pointing to t1
│   Note: t2 and t3 are blocked until t1 completes (dependency)
│
STATE: AWAITING
├── Receive [result id=t1 s=ok] from Coder   (M4)
│   └── Now t2 and t3 can resolve their context-ref → unblock
├── Receive [result id=t2 s=ok] from Reviewer (M5)
├── Receive [result id=t3 s=ok] from Tester  (M6)
│   └── All results received → transition to AGGREGATING
│
STATE: AGGREGATING
├── Main agent loads all 3 results
├── Main agent expands DSL→NL
├── Main agent checks for conflicts:
│   - Reviewer approves, but tests have 1 failure
│   - Both are valid:approve + test failure is a real state
│   - NL synthesis must mention both
├── Main agent generates NL summary (M7)
│
STATE: COMPLETE
├── NL summary delivered to user
└── Process ends
```

### What happens if things fail?

**Scenario: Coder fails**
```
Receive [error id=t1 code=tool-failure] from Coder
├── Retry 1: re-dispatch t1 with same context
├── Receive [error id=t1 code=tool-failure] again
├── Retry 2: re-dispatch with narrowed scope + explicit file paths
├── Receive [error id=t1 code=tool-failure] again  
├── Retry 3: ESCALATE
└── NL to user: "I couldn't modify the handler file after 
    3 attempts. Permission issue with src/handlers/user.py. 
    Can you check the file permissions?"
```

**Scenario: Reviewer blocked on Coder**
```
[task id=t2] dispatched but context-ref=t1 unresolved
├── Protocol: t2 is "blocked" until t1.result is available
├── Main agent detects the block
├── If t2 is blocked for > timeout → cancel t2, announce partial result
└── NL to user: "Code is done but reviewer couldn't start 
    because of a dependency issue. Here's the code result..."
```

---

## 8. Message Ordering Guarantees

### 8.1 Ordering Rules

1. A `[task]` MUST be dispatched before a `[result]` for that task ID.
2. A `context-ref` MUST point to a message that has already been delivered.
3. `[result]` messages MAY arrive in any order (parallel subagents).
4. `[cancel]` MUST reference a task that is `DISPATCHED` or `IN_PROGRESS`.
5. Within a single message, child tags appear in schema-defined order (core → domain → unknown).

### 8.2 Idempotency

Messages with the same `id` and identical content are idempotent. Subagents MUST handle duplicate task dispatches (from retries) gracefully:
- If the task was already completed, return the cached result.
- If the task was partially completed, resume from the last checkpoint (PoC: just re-run).

---

## 9. Protocol Message Summary

### Full Message Type Table

| Type | Dir | Attrs | Description |
|------|-----|-------|-------------|
| `task` | M→S | `id`, `type` | Assign work |
| `result` | S→M | `id`, `s` | Report completion |
| `cancel` | M→S | `id`, `reason` | Cancel task |
| `ask` | S→M | `id`, `question` | Clarification request |
| `progress` | S→M | `id`, `pct` | Heartbeat (optional PoC) |
| `error` | S→M | `id`, `code`, `sev` | Infrastructure failure |
| `answer` | M→S | `id` | Response to `ask` |
| `proceed` | M→S | `id` | Tell subagent to continue |
| `summary` | M→M | `refs` | Self-summarize for context mgmt |

M = Main Agent, S = Subagent

---

## 10. Design Decisions & Rationale

### Why no direct subagent-to-subagent communication?

Keeps the protocol simple. Every subagent is stateless with respect to other subagents. The main agent is the single coordination point. This avoids:
- Message routing complexity
- Race conditions between subagents  
- Circular dependencies
- Fan-out explosion of connections

### Why separate `[error]` from `[result s=fail]`?

`[result s=fail]` means "I tried the task and couldn't complete it" — the subagent did its best. `[error]` means "something broke at the infrastructure level" — the subagent couldn't even attempt the task. The retry policy differs:
- `s=fail` → narrower scope retry or re-ask
- `error` → same-scope retry with backoff

### Why deterministic message ordering?

Makes the protocol testable. Given the same inputs and same subagent behavior, the main agent should produce the same dispatch sequence and the same NL output every time.

### Why lossy summarization instead of full compression?

Full lossless compression of DSL → DSL is possible but expensive (requires another LLM call). Lossy summarization is cheaper and sufficient for the use case: the main agent only needs the key facts to generate a good NL summary. The full DSL is still available in the message log for audit/debugging.

### Why sequential simulation for PoC?

Real concurrent execution requires async runtime, message queues, and race condition handling. For PoC validation of the DSL concept, sequential simulation is sufficient. The protocol is designed to support concurrency (message-level, not execution-level).

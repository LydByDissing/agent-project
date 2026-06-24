# SDD Rules — Shared Reference

Read this file at the start of every `plan`, `implement`, and `arch-review` skill
invocation. It is the single source of truth for standards that cross skill boundaries.

---

## Test Requirements

Every feature MUST have tests. No exceptions.

| Component type | Required test type | Default framework |
|---|---|---|
| Business logic / service | Unit tests | pytest |
| API endpoints | Integration tests | pytest + httpx |
| Data access / repository | Integration tests (real DB) | pytest + SQLAlchemy |
| CLI / script | End-to-end | pytest |
| UI component | Component tests | per project ADR |

**Framework selection**: ask the user once per project. Record the decision in
`docs/specs/adrs/` as an ADR before any test work begins. Do not ask again once
an ADR exists for testing.

Never mock the database in integration tests. Mocked tests have historically
passed while production migrations failed — we test against real data stores.

---

## Model Selection

| Role | Default | Escalate to |
|---|---|---|
| coder | haiku | sonnet: refactor >3 files, auth/payments/security, new architectural boundary |
| reviewer | sonnet | opus: auth, payments, data migration, public API surface changes |
| tester | haiku | sonnet: if test coverage is inadequate in practice |
| arch-review | sonnet | opus: major architectural decisions, compliance-sensitive changes |

Model is encoded in the `[exec]` block `[job model=...]`. Conductor reads and applies it;
no heuristics in the executor.

---

## Code Style

Sub-agents generating code MUST follow these rules. No exceptions.

### Naming
- Functions: `snake_case`, abbreviated but inferrable (`val_email` not `validate_email_address`)
- Classes: `PascalCase`, abbreviated (`EmailVal` not `EmailValidator`)
- Local variables: Go-style short (`n`, `r`, `buf`, `err`, `ok`, `fn`, `val`, `idx`)

### Comments
- No docstrings. Ever.
- No inline comments.
- Type hints on public functions only. Not on private helpers or local variables.

### Formatting
- No blank lines between class methods.
- Single blank line between top-level functions.
- f-strings only for string interpolation.
- List/dict comprehensions instead of explicit loops for single-line operations.
- Use `...` not `pass` in stubs or abstract methods.
- No blank lines between import groups (stdlib, third-party, local all contiguous).

---

## [origin] Header Convention

Every source or test file created or materially modified by a worker MUST carry
an `[origin]` header at the top.

```
# [origin ref=<bd_id> req=REQ-XXX c4=<container>/<component>]
#   [intent]<one sentence — what this file does, not how>[/intent]
#   [inv]<falsifiable invariant arch-review can check>[/inv]
# [/origin]
```

- `ref=`: bd issue ID. Newest first, comma-separated when multiple issues have
  touched the file.
- `req=`: the requirement being implemented.
- `c4=`: `container/component` from the C4 L3 mapping. Must match the
  `c4_component` field on the requirement in docs.
- `[inv]`: optional. A falsifiable claim (e.g. "token is always invalid after 24h").
  arch-review uses these as checkpoints.

**On new files**: write the full header.

**On existing files with an [origin] header**: prepend the new `<bd_id>` to `ref=`
(newest first). Update `[intent]` only if the change materially shifts purpose.
Leave `[inv]` in place unless it is now wrong.

**Skip on**: pure config files (.toml, .json, fixtures), lockfiles, generated
build output, files you only deleted.

Comment prefix by language:
- `#` — Python, shell, YAML, TOML
- `//` — JS, TS, Go, Rust, Java, C, C++
- `--` — SQL, Lua, Haskell

---

## DSL Wire Format

### Task (plan → worker, stored as bd issue body)

```
[task id=<id> type=code|review|test]
[req id=<req-id>]
[c4 component=<name> container=<name>]
[component]
  <C4 L3 component description — patterns, ownership, interfaces>
[/component]
[container]
  <C4 L2 container context — tech stack, what calls this, what it calls>
[/container]
[goal]<objective>[/goal]
[why]<one sentence rationale — the business reason this exists>[/why]
[accept]<verbatim acceptance criterion from the requirement>[/accept]
[non-goal]<explicit exclusions>[/non-goal]
[file read=<path>]
[out <path>]
[/task]
```

### Result (worker → conductor, written to bd issue body)

```
[result id=<id> s=ok|partial|fail|blocked]
[artifact path=<path> a=new|mod|del n=<lines>]
[suite t=<total> p=<pass> f=<fail>]
  [test name=<name> s=fail reason=<text>]
[/suite]
[verdict approve|request-changes|block]
[note sev=crit|major|minor|info at=<file>:<line>]<text>[/note]
[new-req]<description of newly discovered requirement>[/new-req]
[/result]
```

`[new-req]` is a reset signal. When present, `sdd` bounces the entire pipeline
back to the docs phase. Never work around a missing requirement — surface it.

### Exec (plan → conductor)

```
[exec run=<run_id> feat=<feat-id>]
[job id=<bd_id> role=coder|reviewer|tester model=haiku|sonnet|opus]
[job id=<bd_id> role=reviewer model=sonnet depends=<bd_id>]
[/exec]
```

### Synthesis (conductor → sdd)

```
[synthesis run=<run_id> feat=<feat-id> s=ok|partial|fail|reset]
[job id=<bd_id> role=<role> s=ok|fail]
[req id=<req-id> s=done|partial|fail tasks=<closed>/<total>]
[new-req src=<bd_id>]<description>[/new-req]
[/synthesis]
```

`s=reset` means at least one worker emitted `[new-req]`. `sdd` must bounce to docs.

### Attribute quick-ref

| Abbrev | Meaning |
|---|---|
| `s=` | status: `ok` / `fail` / `blocked` / `partial` / `reset` |
| `a=` | file action: `new` / `mod` / `del` |
| `n=` | line count |
| `t=` `p=` `f=` | suite total / pass / fail |
| `sev=` | severity: `crit` / `major` / `minor` / `info` |
| `at=` | file:line location |

---

## Common bd Commands

```bash
bd show <id>                                   # Read issue + body + acceptance criteria
bd list --label "feat=FEAT-XXX"                # All issues for a feature
bd list --label "run=$RUN_ID" --status open    # Stalled issues in a run
bd ready                                       # Unblocked issues
bd blocked                                     # Blocked issues
bd dep add <child> --depends-on <parent>
bd close <id>
bd epic create "<title>"                       # Create SDD run epic
bd epic show <id>                              # Read epic state
```

# [origin ref=llm-dsl-l3a,llm-dsl-0p1 req=REQ-TRACER-BULLETS-001,REQ-TRACER-BULLETS-002,REQ-TRACER-BULLETS-003,REQ-TRACER-BULLETS-004 c4=sdd_skills/plan_skill]
#   [intent]Shared reference documentation for DSL format, code style, model selection, and testing rules across all SDD pipeline roles[/intent]
# [/origin]

# SDD Rules — Shared Reference

Read only the sections relevant to your role:

| Role | Read |
|---|---|
| coder | Code Style, [origin] Header, DSL → Result format |
| tester | [origin] Header, DSL → Result format, Test Requirements row in table |
| reviewer | DSL → Result format, bd Commands |
| conductor | DSL → Exec + Synthesis formats, bd Commands |
| plan | DSL → Task format, Model Selection, bd Commands |
| arch-review | DSL → Result format, [origin] Header, bd Commands |

Every role also reads `skills/rules/CODEGRAPH.md` — how to query the project's
code graph instead of grepping for structural facts.

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
`docs/source/specs/adrs/` as an ADR before any test work begins. Do not ask again once
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

Sub-agents generating code MUST follow the section for the language they are
writing. Apply **one** language section — they conflict with each other by
design, because they encode different communities' conventions.

If the project's own `CLAUDE.md` or the surrounding code disagrees with a rule
here, **the project wins**. Consistency inside a codebase beats consistency with
this document.

### Language-agnostic

These hold regardless of language:

- **Fail loudly, and name the offending value.** Never return a sentinel that a
  caller could mistake for a real answer. A zero returned for "no benchmark
  mapped" reads as "performed exactly in line with the benchmark" — a wrong
  answer wearing the costume of a right one.
- **Absent is not zero.** If a value can be genuinely missing, represent that
  distinctly. Coercing absent to `0`, `""` or `false` destroys information
  silently and the failure surfaces far from its cause.
- **Determinism where output is compared, hashed or persisted.** No unordered
  map iteration, no wall-clock reads below an entry point, no locale-sensitive
  formatting. Pass time in as a parameter.
- **Never catch-and-substitute across an abstraction boundary.** A failed call
  to one implementation must not silently become another's answer.

### Python

- Functions: `snake_case`, abbreviated but inferrable (`val_email` not
  `validate_email_address`)
- Classes: `PascalCase`, abbreviated (`EmailVal` not `EmailValidator`)
- Local variables: Go-style short (`n`, `r`, `buf`, `err`, `ok`, `fn`, `val`, `idx`)
- No docstrings. Ever. No inline comments.
- Type hints on public functions only. Not on private helpers or locals.
- No blank lines between class methods; single blank line between top-level
  functions.
- f-strings only for string interpolation.
- List/dict comprehensions instead of explicit loops for single-line operations.
- Use `...` not `pass` in stubs or abstract methods.
- No blank lines between import groups (stdlib, third-party, local contiguous).

### Java

Do **not** apply the Python naming or comment rules to Java. They fight the
language and the tooling.

**Naming** — standard Java, no exceptions:
- Types `PascalCase`, methods and fields `camelCase`, constants
  `UPPER_SNAKE_CASE`, packages lowercase single words.
- Abbreviate only where the short form is unambiguous in context. Locals may be
  short (`n`, `buf`, `ok`); fields and methods may not.
- One top-level type per file, and the filename must match the public type
  exactly — the compiler requires it, and `foo_barTest.java` holding
  `foo_barTest` is a defect even though it compiles.

**Types and immutability**
- `record` for immutable value objects; `sealed interface` plus records for a
  closed hierarchy.
- Defensive-copy collections on the way in (`List.copyOf`, `Map.copyOf`).
- `Optional<T>` for genuinely absent values. Never coerce an empty Optional to a
  sentinel on the way into storage or serialisation.
- `BigDecimal` for money, prices and anything aggregated — never `double`.
  Always set scale and `RoundingMode` explicitly; never rely on default
  `toString` of a floating-point type.

**Documentation** — this overrides the Python "no docstrings" rule:
- Javadoc on public types and methods whose contract is not obvious from the
  signature. Javadoc is the Java convention and the tooling reads it.
- No narrating comments restating the code. Comment the non-obvious *why*.
- Keep the `[inv]` line in the `[origin]` header falsifiable and true — a
  reviewer may test it by deliberately breaking the invariant.

**Errors**
- Throw a *named* domain exception when a caller may need to distinguish causes;
  a bare `RuntimeException` forces callers to string-match.
- Distinguish transient transport failures from genuine domain failures. Folding
  them together corrupts any dataset that records outcomes.

**Spring**
- Constructor injection only. No field or setter injection.
- Group configuration into `@ConfigurationProperties` records rather than
  scattering `@Value`. **Exactly one place may define the default for a given
  setting** — two defaults for one value will drift, and the one that loses is
  invisible.
- Enforce invariants that must hold regardless of call path with lifecycle
  callbacks (e.g. `@PreUpdate`) rather than only in the service layer, which
  callers can bypass.

**Formatting**
- Four-space indent, no tabs. Follow the surrounding file.
- No wildcard imports. Static imports only for test assertions.

**Testing (JUnit 5 + Surefire)**
- Name tests `test_<what>_<condition>_<expected_outcome>`.
- Arrange / Act / Assert. One behaviour per test.
- Assert **exact expected values**. Never assert merely non-null.
- **Assert a collection is non-empty before asserting a property over its
  elements.** A `for` loop over an empty list passes every assertion inside it
  and verifies nothing — this is the single most common way a green suite hides
  a broken component.
- Never mock the database, or an external API you can actually reach. Use the
  real store and a real test/paper endpoint.
- Never disable, skip or exclude a failing test to obtain a green build, and
  never weaken an assertion to make one pass. A build that is green because a
  test was excluded is not green.
- Where a test enforces a boundary or a guard, add a **positive control** that
  proves the check can actually fire. A scan that matches nothing passes
  silently and forever.

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
[task id=<id> type=code|review|test|prefactor]
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

**type field**: Includes new `prefactor` type for scaffolding/infrastructure work that other
tasks depend on. Prefactor tasks appear first in exec block ordering.

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

`[new-req]` carries a **severity**, because not every discovered requirement
justifies resetting the pipeline:

```
[new-req sev=blocks-milestone]<description>[/new-req]   → sdd resets to docs now
[new-req sev=blocks-slice]<description>[/new-req]       → this slice stops; siblings continue
[new-req sev=noted]<description>[/new-req]              → record and continue
```

- `blocks-milestone` — the feature cannot be correct without it. Reset to docs.
- `blocks-slice` — this task cannot finish, but other work is unaffected. The
  conductor records it, leaves the issue open, and continues the remaining waves.
- `noted` — a real gap that does not prevent the current work being correct.
  Amend the docs, file a tracked issue, carry on.

Absent severity means `blocks-milestone`, so an unqualified `[new-req]` is still
a full reset.

**In every case: never work around a missing requirement.** Surface it. A worker
that quietly invents the missing behaviour is worse than one that stops, because
the invention becomes an unrecorded decision nobody reviews.

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

**Verify these against `bd --help` before relying on them — the CLI has changed
shape before and the failure messages are misleading.** Known gotchas:

- **One label per `bd label add` call.** Extra positional arguments are parsed as
  *issue IDs*, so a multi-label call fails with
  `Error resolving phase=docs: no issue found matching "phase=docs"` — which
  looks like a missing issue, not a syntax error.
- **Labels are additive.** Changing a value means `bd label remove <id> "phase=docs"`
  then `bd label add <id> "phase=plan"`. Adding alone leaves both, and later reads
  see whichever comes first.
- **`bd close` on an issue with open blockers silently no-ops.** It reports
  `cannot close … blocked by open issues [<id>] (use --force to override)` and
  returns non-zero — easy to miss in a loop that discards output. Use `--force`
  only for genuinely superseded work.
- **`bd init --prefix <p>` is required first.** Without it commands fail without
  saying the database is missing.

```bash
bd show <id>                                   # Read issue + body + acceptance criteria
bd list --label "feat=FEAT-XXX"                # All issues for a feature
bd list --label "run=$RUN_ID" --status open    # Stalled issues in a run
bd ready                                       # Unblocked issues
bd blocked                                     # Blocked issues
bd dep add <child> <parent>
bd close <id>
bd create --type epic "<title>"                       # Create SDD run epic
bd show <id>                              # Read epic state
```

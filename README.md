# agent-project

A Claude Code plugin for **Spec-Driven Development (SDD)** — an autonomous
multi-agent pipeline that takes a feature from specification to reviewed,
tested code without the user having to manage the steps.

## How it works

The user writes (or the `docs` skill helps write) a specification. Everything
downstream is driven by that spec: planning, implementation, testing, and
architecture review are all autonomous. The user touches three gates:

```
docs ──[approve docs]──► plan ──[approve plan]──► implement ──► arch-review ──[approve]──► done
 ▲                        │                           │               │
 └─────────── new requirement discovered (any phase resets here) ─────┘
```

If any phase discovers a requirement that isn't in the specification, the
pipeline resets to `docs` rather than working around the gap. Specs stay
complete.

## Skills

| Skill | Invoked by | Purpose |
|---|---|---|
| `sdd` | user | Entry point. Creates a bd epic, drives the pipeline, manages resets |
| `docs` | sdd or user | C4 interview, sphinx-needs requirements, ADRs, Sphinx site |
| `plan` | sdd | Preflight checks, decompose into tasks, confirm gate, create bd issues |
| `conductor` | sdd | Wave-based worker spawner, dependency ordering, synthesis |
| `implement` | conductor | Coder, tester, and reviewer worker behavior |
| `arch-review` | sdd | Test quality sensors, REQ coverage, C4 boundary, ADR compliance |

`skills/rules/RULES.md` and `skills/rules/TESTING.md` are shared references
read by the agent skills — not user-invokable.

## State

State lives in **bd (beads)**, the project's issue tracker. A bd epic
represents one SDD run. Issues inside it are the agent work items, each
carrying a compact DSL brief derived from the specification. Docs are the
human-readable truth; bd issues are the agent-facing digests of that truth.

## Specification format

Specifications live in `docs/specs/` as reStructuredText, tracked with
[sphinx-needs](https://sphinx-needs.com). Three directive types:

```rst
.. feat:: User Authentication
   :id: FEAT-AUTH
   :status: approved

   Users must be able to log in with email and password.

.. req:: Password login returns JWT
   :id: REQ-AUTH-001
   :links: FEAT-AUTH
   :rationale: Stateless tokens allow horizontal scaling without session state.
   :acceptance: Valid credentials return a signed JWT within 500ms.
   :non_goal: OAuth, SSO, password reset.
   :c4_component: auth_service
   :c4_container: backend

   The system shall authenticate users via email/password and issue a signed JWT.

.. adr:: Use JWT over server-side sessions
   :id: ADR-003
   :status: accepted

   **Decision**: Issue JWTs on login; no server-side session store.
   **Rationale**: Stateless; scales horizontally without sticky sessions.
```

Requirements link to C4 components. Planning cannot start until all
requirements for a feature are mapped to a C4 component — the component
description is the design document that guides implementation.

## Architecture docs

Architecture lives in `docs/architecture/`, following the
[C4 model](https://c4model.com):

- `context.rst` — L1: system and external actors
- `containers.rst` — L2: deployable units and their relationships
- `components/<name>.rst` — L3: internals of each container

The L3 component descriptions are the implementation guide. They carry
pattern choices, ownership boundaries, and what each component does not do.
Plan reads them to produce fully-contextual bd task briefs.

## Getting started

```bash
# Install docs dependencies
pip install -r docs/requirements.txt   # sphinx, furo, sphinx-needs

# Bootstrap a new project's docs site (idempotent)
python skills/docs/scripts/bootstrap_sphinx.py

# Start a feature (docs skill runs first if spec is incomplete)
/sdd FEAT-AUTH
```

## Project layout

```
skills/
├── sdd/          SKILL.md        — pipeline entry point
├── docs/         SKILL.md        — documentation + specification skill
│                 scripts/        — bootstrap_sphinx.py, generate_diagrams.py
│                 references/     — C4 and ArchiMate element reference
├── plan/         SKILL.md        — planning and bd issue creation
├── conductor/    SKILL.md        — wave-based worker orchestration
├── implement/    SKILL.md        — coder, tester, reviewer worker behavior
├── arch-review/  SKILL.md        — architecture and test quality review
│                 scripts/        — lint_tests.py (static test sensor)
└── rules/        RULES.md        — DSL format, code style, model selection
                  TESTING.md      — test quality guide and anti-patterns
```

## License

Apache-2.0

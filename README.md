# LLM-DSL

A domain-specific language for efficient LLM-to-LLM communication in multi-agent workflows.

## Problem

As LLMs become more capable, token usage increases, making agent workloads expensive and slow. We need to minimize tokens without losing expressiveness.

## Solution

LLM-DSL is a compact bracket-tag protocol for inter-agent communication:

- **Natural language at the edges** — users talk to the main agent in NL
- **DSL between agents** — subagents communicate via compact structured messages
- **Bidirectional translation** — static rules expand DSL back to NL for human consumption
- **Reference-based** — agents reference prior data instead of re-sending it

## Token Savings

In the validation testcase (3-agent code review pipeline):
- **24% overall token savings** on inter-agent messages
- Savings compound on larger/iterative workflows
- Reference-based context sharing avoids re-sending artifacts

## Architecture

```
User (NL) → Main Agent → [DSL] → Subagents → [DSL] → Main Agent → (NL) → User
```

## Run the PoC

```bash
python3 tests/test_validation.py
```

This runs the full validation testcase with all 7 acceptance criteria:
1. Round-trip fidelity (DSL → parse → serialize → DSL)
2. Token savings (DSL < NL)
3. Composability (context-ref works)
4. Aggregation (3 results → 1 NL summary)
5. Determinism (same data → same output)
6. Schema resilience (unknown fields preserved)
7. Process declaration (topology in one file)

## Project Structure

```
src/
  dsl_parser.py        - DSL wire form → structured data
  dsl_serializer.py    - Structured data → DSL wire form
  translator.py        - Static DSL → NL translation
  process_loader.py    - Load/validate process.yaml definitions
  harness.py           - Agent orchestration + simulation
tests/
  test_validation.py   - End-to-end validation testcase
process.yaml           - Validation testcase process definition
docs/
  validation-testcase.md
  design/
    message-schema.md
    communication-protocol.md
    agent-process.md
    schema-drift.md
    bootstrapping.md
    human-output.md
    static-translator.md

## Design Documents

- [Message Schema](docs/design/message-schema.md) — DSL syntax, types, core schema
- [Communication Protocol](docs/design/communication-protocol.md) — State machine, dispatch patterns, error handling
- [Agent Process](docs/design/agent-process.md) — Process definition format, composition primitives
- [Schema Drift](docs/design/schema-drift.md) — Unknown field passthrough, validation modes
- [Bootstrapping](docs/design/bootstrapping.md) — System prompt construction, context budget
- [Human Output](docs/design/human-output.md) — DSL→NL rendering, templates
- [Static Translator](docs/design/static-translator.md) — Translation architecture

## License

MIT

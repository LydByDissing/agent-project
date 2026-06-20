# Validation Strategy

## Current State

The PoC has 7/7 passing acceptance criteria, but all tests use **hardcoded** subagent responses. The fundamental unvalidated assumption is:

> **Will a real LLM actually produce valid DSL when instructed to do so?**

Everything else (parser, serializer, translator, token savings) depends on this.

## Validation Levels

### Level 1: Unit Tests (DONE)

Tests that don't require an LLM:
- Parser round-trip (wire → parse → wire)
- Serializer determinism
- Template expansion correctness
- Process definition loading/validation

**Status:** ✅ Complete in `tests/test_validation.py`

### Level 2: LLM Compliance Test (NEXT)

**Goal:** Verify that a real LLM produces valid DSL output when given proper instructions.

**Method:**
1. Give an LLM the DSL schema reference + a task
2. Ask it to produce a `[result]` message in DSL
3. Run the output through the parser
4. Check: does it parse? Is information preserved?

**What this validates:**
- LLM can follow the DSL format
- Parser handles real LLM output (not just hand-crafted)
- Schema reference in system prompt is sufficient

**How to run without API costs:**
- Use a local model (ollama, llama.cpp) with the DSL schema in the prompt
- Or use the cheapest available API model (GPT-4o-mini, Claude Haiku)
- 10-20 test runs is sufficient for PoC validation

### Level 3: End-to-End with Real LLM

**Goal:** Run the full pipeline with a real LLM as the main agent.

**Method:**
1. Main agent (real LLM) receives user NL input
2. Main agent produces DSL task messages (validated by parser)
3. Subagent (real LLM) receives DSL task, produces DSL result
4. Main agent aggregates DSL results → NL for user

**What this validates:**
- Full pipeline works end-to-end
- Token savings with real output
- NL output quality is acceptable

### Level 4: Comparative Benchmark

**Goal:** Quantify the benefit vs. cost of using DSL.

**Method:**
- Run the same task in two modes: DSL and pure NL
- Measure: token count, latency, output quality
- Test at different scales: 1 hop, 3 hops, 10 hops, iterative loops

## Recommended Next Step: Level 2

Level 2 is the highest-value next step because:
- It's cheap (10-20 LLM calls)
- It validates the core assumption
- It exercises the parser with real output
- It can be done locally (no API costs)

If Level 2 fails (LLM can't produce valid DSL), we need to iterate on:
- The schema reference format (make it simpler/clearer)
- The parser (make it more forgiving)
- The prompt instructions (be more explicit)

If Level 2 passes, we have confidence the concept works and can proceed to Level 3.

"""
Benchmark: DSL vs NL token usage in multi-agent workflows.

Measures actual token counts for DSL and NL representations of the same
workflow data, at different scales (1 step, 3 steps, 10 steps, iterative).

Usage:
  python3 tests/test_benchmark.py
"""

import sys
import os
import tiktoken

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dsl_parser import parse_dsl


def count_tokens(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


# ── NL messages ──

NL_IMPLEMENT = (
    "I have completed the implementation of input validation for the POST /users endpoint. "
    "I created a new function called validate_user_input() in src/validation/user_schema.py "
    "that takes a RequestBody and returns a ValidationResult object. The function validates "
    "email format using a regex, checks that name is present and within the 100 character limit, "
    "and verifies that age falls within the 0 to 150 range when provided. For the file changes, "
    "I modified src/handlers/user.py adding 23 lines of validation logic, and created a new "
    "file src/validation/user_schema.py with 18 lines defining the validation schema. "
    "The cyclomatic complexity increased by 2 due to the validation branching logic."
)

NL_REVIEW = (
    "I have completed my review of the validation code. Overall verdict: Approved. "
    "I found one minor issue at src/handlers/user.py line 34: the email validation regex "
    "does not support international domain names. I would recommend considering using a "
    "dedicated library like email-validator for more robust email validation in the future. "
    "On the security front, the check passed — SQL injection is not applicable here since "
    "the code uses an ORM for database operations. Code style also passed — the code is "
    "clean and well-structured."
)

NL_TEST = (
    "I have completed writing and running the tests. I created the test file "
    "tests/test_validation.py with 45 lines covering all the required test cases. "
    "The test results show 7 of 8 tests passing, with 1 failure. The passing tests are: "
    "test_valid_input, test_invalid_email, test_missing_name, test_age_high, "
    "test_age_low, test_boundary, test_concurrent. The failing test is "
    "test_sql_injection, which failed because input is not being sanitized — "
    "SQL special characters in the name field pass through to the database layer."
)

NL_SUMMARY = (
    "All tasks completed successfully. Here is a summary:\n\n"
    "Code: Added validate_user_input() with field rules for email format, name length "
    "(max 100), and age range (0-150). Returns 422 with standard error format on "
    "invalid input. Modified src/handlers/user.py (+23 lines) and created "
    "src/validation/user_schema.py (18 lines).\n\n"
    "Review: Approved with one minor note — the email regex doesn't support international "
    "domains. Consider switching to the email-validator library later. "
    "Security: Pass — SQL injection not applicable, uses ORM. Style: Pass.\n\n"
    "Tests: 7 of 8 pass. One failure: SQL injection characters in the name field "
    "pass through to the database.\n\n"
    "Files changed: src/handlers/user.py (+23 lines), "
    "src/validation/user_schema.py (new), "
    "tests/test_validation.py (new)."
)


# ── DSL messages ──

DSL_IMPLEMENT = (
    '[result id=t1 s=ok]'
    '[artifact a=mod n=+23 path=src/handlers/user.py]'
    '[artifact a=new n=18 path=src/validation/user_schema.py]'
    '[added fn=validate_user_input in:RequestBody out:ValidationResult]'
    '[complexity delta="+2cyclomatic"]'
    '[/result]'
)

DSL_REVIEW = (
    '[result id=t2 s=ok]'
    '[verdict approve]'
    '[note at=src/handlers/user.py:34 sev=minor]'
    'Email regex does not support international domains. '
    'Consider using email-validator library.'
    '[/note]'
    '[/result]'
)

DSL_TEST = (
    '[result id=t3 s=ok]'
    '[artifact a=new n=45 path=tests/test_validation.py]'
    '[suite f=1 p=7 t=8]'
    '[test name=test_valid_input s=pass]'
    '[test name=test_invalid_email s=pass]'
    '[test name=test_missing_name s=pass]'
    '[test name=test_age_high s=pass]'
    '[test name=test_age_low s=pass]'
    '[test name=test_boundary s=pass]'
    '[test name=test_concurrent s=pass]'
    '[test name=test_sql_injection reason="SQL chars not sanitized" s=fail]'
    '[/suite]'
    '[/result]'
)

DSL_SUMMARY = (
    '[summary id=s1 s=ok]'
    '[agent s=ok type=coder]'
    '[files added=21 changed=2 removed=0]'
    '[artifacts a=mod path=src/handlers/user.py]'
    '[artifacts a=new path=src/validation/user_schema.py]'
    '[/agent]'
    '[agent s=ok type=reviewer]'
    '[verdict approve]'
    '[findings count=1 sev=minor]'
    '[/agent]'
    '[agent s=ok type=tester]'
    '[tests f=1 p=7 t=8]'
    '[failures name=test_sql_injection reason="SQL chars not sanitized"]'
    '[/agent]'
    '[action-items]'
    '[item]Use email-validator library for international domains[/item]'
    '[item]Add SQL sanitization for name field[/item]'
    '[/action-items]'
    '[/summary]'
)


# ── Benchmarks ──

def benchmark_single_task():
    """Compare NL vs DSL for a single task."""
    print("\n=== Single Task (Implement) ===")
    nl_tok = count_tokens(NL_IMPLEMENT)
    dsl_tok = count_tokens(DSL_IMPLEMENT)
    savings = (1 - dsl_tok / nl_tok) * 100
    print(f"  NL:  {nl_tok} tokens ({len(NL_IMPLEMENT)} chars)")
    print(f"  DSL: {dsl_tok} tokens ({len(DSL_IMPLEMENT)} chars)")
    print(f"  Savings: {savings:.1f}%")
    return nl_tok, dsl_tok


def benchmark_3step():
    """Compare NL vs DSL for implement + review + test."""
    print("\n=== 3-Step Pipeline (Implement + Review + Test) ===")
    nl = NL_IMPLEMENT + "\n\n" + NL_REVIEW + "\n\n" + NL_TEST
    dsl = DSL_IMPLEMENT + DSL_REVIEW + DSL_TEST
    nl_tok = count_tokens(nl)
    dsl_tok = count_tokens(dsl)
    savings = (1 - dsl_tok / nl_tok) * 100
    print(f"  NL:  {nl_tok} tokens ({len(nl)} chars)")
    print(f"  DSL: {dsl_tok} tokens ({len(dsl)} chars)")
    print(f"  Savings: {savings:.1f}%")
    return nl_tok, dsl_tok


def benchmark_full_pipeline():
    """Compare NL vs DSL for full pipeline including summary."""
    print("\n=== Full Pipeline (3 tasks + summary) ===")
    nl = NL_IMPLEMENT + "\n\n" + NL_REVIEW + "\n\n" + NL_TEST + "\n\n" + NL_SUMMARY
    dsl = DSL_IMPLEMENT + DSL_REVIEW + DSL_TEST + DSL_SUMMARY
    nl_tok = count_tokens(nl)
    dsl_tok = count_tokens(dsl)
    savings = (1 - dsl_tok / nl_tok) * 100
    print(f"  NL:  {nl_tok} tokens ({len(nl)} chars)")
    print(f"  DSL: {dsl_tok} tokens ({len(dsl)} chars)")
    print(f"  Savings: {savings:.1f}%")
    return nl_tok, dsl_tok


def benchmark_iterative(n_iterations=3):
    """Compare NL vs DSL for iterative review-fix cycles."""
    print(f"\n=== Iterative Loop ({n_iterations} review-fix cycles) ===")

    nl_parts = []
    dsl_parts = []
    for i in range(n_iterations):
        nl_parts.append(
            f"Iteration {i+1} Review: Found issue at line {34+i}. "
            f"The validation logic needs adjustment. Request changes."
            f"\n\n"
            f"Iteration {i+1} Fix: I have addressed the review findings. "
            f"Modified src/handlers/user.py adding {5+i} lines of additional "
            f"validation logic. All tests pass now."
        )
        dsl_parts.append(
            f'[result id=t{i+10} s=ok]'
            f'[note at=src/handlers/user.py:{34+i} sev=minor]'
            f'Validation logic needs adjustment'
            f'[/note]'
            f'[verdict request-changes]'
            f'[/result]'
            f'[result id=t{i+11} s=ok]'
            f'[artifact a=mod n="+{5+i}" path=src/handlers/user.py]'
            f'[/result]'
        )

    nl = "\n\n".join(nl_parts)
    dsl = "".join(dsl_parts)
    nl_tok = count_tokens(nl)
    dsl_tok = count_tokens(dsl)
    savings = (1 - dsl_tok / nl_tok) * 100
    print(f"  NL:  {nl_tok} tokens ({len(nl)} chars)")
    print(f"  DSL: {dsl_tok} tokens ({len(dsl)} chars)")
    print(f"  Savings: {savings:.1f}%")
    return nl_tok, dsl_tok


def benchmark_context_accumulation(n_steps=5):
    """
    Simulate context window accumulation.
    In NL, each step re-describes prior context.
    In DSL, each step only adds its own compact result.
    """
    print(f"\n=== Context Accumulation ({n_steps} steps) ===")

    nl_total = 0
    dsl_total = 0
    for i in range(n_steps):
        nl_msg = (
            f"Step {i+1}: I have completed step {i+1}. "
            f"Working on feature X. Modified file_{i+1}.py adding {10+i*5} lines. "
            f"Prior steps completed: {', '.join(f'Step {j+1}' for j in range(i))}. "
            f"All tests pass."
        )
        dsl_msg = (
            f'[result id=t{i+1} s=ok]'
            f'[artifact a=mod n="+{10+i*5}" path=file_{i+1}.py]'
            f'[/result]'
        )
        nl_total += count_tokens(nl_msg)
        dsl_total += count_tokens(dsl_msg)

    savings = (1 - dsl_total / nl_total) * 100
    print(f"  NL total:  {nl_total} tokens ({n_steps} messages)")
    print(f"  DSL total: {dsl_total} tokens ({n_steps} messages)")
    print(f"  Savings: {savings:.1f}%")
    return nl_total, dsl_total


def benchmark_round_trip_fidelity():
    """Verify DSL round-trip preserves all information."""
    print("\n=== Round-Trip Fidelity ===")

    parsed = parse_dsl(DSL_IMPLEMENT)
    reserialized = parsed.to_wire()

    checks = [
        ("s=ok", parsed.attrs.get("s") == "ok"),
        ("artifact count", len(parsed.children_by_tag("artifact")) == 2),
        ("file paths", all(
            a.get_attr("path") in ["src/handlers/user.py", "src/validation/user_schema.py"]
            for a in parsed.children_by_tag("artifact")
        )),
        ("action types", all(
            a.get_attr("a") in ["mod", "new"]
            for a in parsed.children_by_tag("artifact")
        )),
        ("line counts", all(
            a.get_attr("n") in ["+23", "18"]
            for a in parsed.children_by_tag("artifact")
        )),
        ("added fn", parsed.child("added").get_attr("fn") == "validate_user_input"),
        ("complexity", parsed.child("complexity").get_attr("delta") == "+2cyclomatic"),
        ("round-trip", DSL_IMPLEMENT == reserialized),
    ]

    all_pass = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  {status} — {name}")
        if not passed:
            all_pass = False

    print(f"\n  Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return all_pass


def main():
    print("=" * 60)
    print("LLM-DSL Benchmark: Token Savings Measurement")
    print("=" * 60)
    print(f"Tokenizer: cl100k_base")

    results = {}

    results["single_task"] = benchmark_single_task()
    results["3step"] = benchmark_3step()
    results["full_pipeline"] = benchmark_full_pipeline()
    results["iterative_3"] = benchmark_iterative(3)
    results["context_5"] = benchmark_context_accumulation(5)
    results["fidelity"] = benchmark_round_trip_fidelity()

    # Summary table
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\n{'Scenario':<30} {'NL tokens':>10} {'DSL tokens':>10} {'Savings':>10}")
    print("-" * 62)

    scenarios = [
        ("Single Task", "single_task"),
        ("3-Step Pipeline", "3step"),
        ("Full Pipeline + Summary", "full_pipeline"),
        ("Iterative (3 cycles)", "iterative_3"),
        ("Context Accumulation (5 steps)", "context_5"),
    ]

    for name, key in scenarios:
        nl_tok, dsl_tok = results[key]
        savings = (1 - dsl_tok / nl_tok) * 100
        print(f"  {name:<28} {nl_tok:>10} {dsl_tok:>10} {savings:>9.1f}%")

    avg_savings = sum(
        (1 - results[k][1] / results[k][0]) * 100
        for _, k in scenarios
    ) / len(scenarios)
    print(f"\n  Average savings: {avg_savings:.1f}%")

    # Cost calculation (GPT-4o pricing: $2.50/1M input tokens)
    print("\n  Cost estimate (GPT-4o: $2.50/1M input tokens):")
    total_nl = sum(results[k][0] for _, k in scenarios)
    total_dsl = sum(results[k][1] for _, k in scenarios)
    nl_cost = total_nl * 2.50 / 1_000_000
    dsl_cost = total_dsl * 2.50 / 1_000_000
    print(f"    NL total:  {total_nl:,} tokens = ${nl_cost:.4f}")
    print(f"    DSL total: {total_dsl:,} tokens = ${dsl_cost:.4f}")
    print(f"    Saved:     ${nl_cost - dsl_cost:.4f} ({(1 - dsl_cost/nl_cost)*100:.1f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

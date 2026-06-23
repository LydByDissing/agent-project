"""
Level 2 Validation: LLM Compliance Test via Claude CLI

Validates that a real LLM (Claude) produces valid DSL output when given
proper schema instructions. Uses the Claude Code CLI in non-interactive mode.

Usage:
  # Dry run (print prompts, no LLM calls):
  python3 validation/llm_compliance_test.py --dry-run

  # Run with Claude CLI:
  python3 validation/llm_compliance_test.py

  # Run a single task:
  python3 validation/llm_compliance_test.py --task code-task-1

  # Run with verbose output:
  python3 validation/llm_compliance_test.py --verbose

  # Save results to file:
  python3 validation/llm_compliance_test.py --output results.json
"""

import sys
import os
import json
import subprocess
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dsl_parser import parse_dsl, DslParseError
from src.translator import dsl_to_nl


# ── DSL System Prompt (injected via --append-system-prompt) ──

DSL_SYSTEM_PROMPT = """
## RESPONSE FORMAT: LLM-DSL

You MUST respond using the LLM-DSL bracket-tag format. Do NOT use natural language for structured responses.

### Syntax
[tagname key=value]content[/tagname]

Rules:
- Single line, NO whitespace between tags
- Attributes: key=value (bare) or key="value with spaces" (quoted)
- Leaf tags (no body, no close tag): [tagname attr=value]
- Text content: [tagname]text here[/tagname]
- Enum values: lowercase, short form (ok, mod, new, crit, ...)

### Core Response Tags

[result id=<task-id> s=ok|partial|fail|blocked]
  Your response wrapper. Always use this.

[artifact path=<path> a=new|mod|del n=<N>]
  File changes. Leaf tag. `a` = action, `n` = line count.

[added fn=<name> in:<input-type> out:<output-type>]
  Functions/types added. Leaf tag. Note: in: and out: use colon.

[removed fn=<name>]
  Functions/types removed. Leaf tag.

[suite t=<N> p=<N> f=<N>]
  [test name=<name> s=pass|fail|skip reason=<if-fail>]
  Test results. `t`/`p`/`f` = total/pass/fail counts.

[verdict approve|request-changes|block]
  Review verdict. Text value, leaf-like: [verdict approve]

[note sev=crit|major|minor|info at=<file>:<line>]
  Issue description here
  [/note]
  Review findings use [note] with sev= and at=. A bare [note] with no sev= is free-form text.

### Example: Coder Response

[result id=t1 s=ok]
[artifact a=new n=45 path=src/validator.py]
[artifact a=mod n=+12 path=src/handlers/user.py]
[added fn=validate_user_input in:RequestBody out:ValidationResult]
[complexity delta="+3cyclomatic"]
[/result]

### Example: Reviewer Response

[result id=t2 s=ok]
[verdict approve]
[note at=src/auth.py:23 sev=minor]
Use bcrypt instead of MD5 for password hashing.
[/note]
[/result]

### Example: Tester Response

[result id=t3 s=ok]
[artifact a=new n=60 path=tests/test_cart.py]
[suite f=2 p=12 t=14]
[test name=test_add_item s=pass]
[test name=test_remove_item s=pass]
[test name=test_oversized_item reason="weight limit not enforced" s=fail]
[test name=test_concurrency_race reason="race condition in update" s=fail]
[/suite]
[/result]

Respond with ONLY the DSL message. No explanation, no markdown code fences.
"""


# ── Test Tasks ──

TEST_TASKS = [
    {
        "id": "code-task-1",
        "name": "Code implementation result",
        "type": "coder",
        "prompt": (
            "You implemented a format_currency function. "
            "Created src/utils/currency.py (35 lines). "
            "Modified src/app.py (+8 lines). "
            "Report your results in DSL format."
        ),
        "expected_tags": ["result", "artifact", "added"],
        "expected_status": "ok",
    },
    {
        "id": "review-task-1",
        "name": "Code review result",
        "type": "reviewer",
        "prompt": (
            "You reviewed a PR adding user authentication. "
            "Found: MD5 password hash at src/auth.py:23 (should use bcrypt). "
            "Style is good. Approve with minor findings. "
            "Report your review in DSL format."
        ),
        "expected_tags": ["result", "verdict", "note"],
        "expected_status": "ok",
    },
    {
        "id": "test-task-1",
        "name": "Test results",
        "type": "tester",
        "prompt": (
            "You wrote and ran tests for a shopping cart feature. "
            "Created tests/test_cart.py (60 lines). "
            "12 of 14 tests pass. Failures: test_oversized_item "
            "(weight limit not enforced), test_concurrency_race "
            "(race condition in cart update). "
            "Report results in DSL format."
        ),
        "expected_tags": ["result", "artifact", "suite", "test"],
        "expected_status": "ok",
    },
    {
        "id": "error-task-1",
        "name": "Failed task",
        "type": "coder",
        "prompt": (
            "You tried to implement a Redis cache layer but failed. "
            "Redis server not running, connection refused on localhost:6379. "
            "Unable to complete the task. "
            "Report in DSL format."
        ),
        "expected_tags": ["result"],
        "expected_status": "fail",
    },
    {
        "id": "minimal-task-1",
        "name": "Minimal valid response",
        "type": "coder",
        "prompt": (
            "You fixed a typo in a README file. That's all. "
            "Changed 'fucntion' to 'function' in README.md. "
            "Report in DSL format."
        ),
        "expected_tags": ["result", "artifact"],
        "expected_status": "ok",
    },
]


# ── Claude CLI Interface ──

def call_cli_agent(system_prompt: str, user_prompt: str, agent: str = "pi",
                    model: str = "") -> tuple[str, bool]:
    """Call a CLI agent (pi, claude, etc.) in non-interactive mode.

    Returns: (output_text, success)
    """
    if agent == "claude":
        cmd = [
            "claude",
            "--print",
            "--output-format", "text",
            "--append-system-prompt", system_prompt,
        ]
        if model:
            cmd.extend(["--model", model])
    elif agent == "pi":
        cmd = [
            "pi",
            "--print",
            "--append-system-prompt", system_prompt,
        ]
        if model:
            cmd.extend(["--model", model])
    else:
        return f"Unknown agent: {agent}", False

    cmd.append(user_prompt)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else "(no stderr)"
            return f"CLI error (exit {result.returncode}): {stderr}", False
        return result.stdout.strip(), True
    except subprocess.TimeoutExpired:
        return "CLI timeout (>120s)", False
    except FileNotFoundError:
        return f"{agent} CLI not found in PATH", False


def extract_dsl_from_output(raw: str) -> str:
    """Extract DSL content from LLM output.

    The LLM might add explanations before/after the DSL, or wrap it
    in markdown code fences. Extract just the DSL portion.
    """
    # Remove markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (``` or ```dsl) and last line (```)
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        text = text.strip()

    # Find [result — the start of our DSL
    idx = text.find("[result")
    if idx == -1:
        return text  # No DSL found, return as-is for error reporting

    # Find [/result] — the end of our DSL
    # Search for the LAST occurrence of [/result] after [result
    end_idx = text.rfind("[/result]")
    if end_idx == -1:
        return text[idx:]  # No close tag found

    # Extract from [result to [/result] inclusive
    return text[idx:end_idx + len("[/result]")]


# ── Validation Logic ──

def validate_output(raw_output: str, test_case: dict, verbose: bool = False) -> dict:
    """Validate LLM output against DSL requirements."""
    result = {
        "test_id": test_case["id"],
        "name": test_case["name"],
        "type": test_case["type"],
        "raw_output": raw_output,
        "extracted_dsl": None,
        "has_dsl": False,
        "parses": False,
        "parse_error": None,
        "expected_tags_found": [],
        "expected_tags_missing": [],
        "nl_expansion": None,
        "overall_pass": False,
    }

    # Extract DSL from output
    dsl = extract_dsl_from_output(raw_output)
    result["extracted_dsl"] = dsl
    result["has_dsl"] = "[result" in dsl

    if verbose:
        print(f"  Extracted DSL: {dsl[:100]}...")

    # Parse
    try:
        parsed = parse_dsl(dsl)
        result["parses"] = True

        # Check expected tags
        all_tags = _collect_all_tags(parsed)
        for tag in test_case.get("expected_tags", []):
            if tag in all_tags:
                result["expected_tags_found"].append(tag)
            else:
                result["expected_tags_missing"].append(tag)

        # Check expected status
        if "expected_status" in test_case:
            status = parsed.get_attr("s", "")
            if status == test_case["expected_status"]:
                result["expected_tags_found"].append(f"s={status}")
            else:
                result["expected_tags_missing"].append(
                    f"s={test_case['expected_status']} (got '{status}')"
                )

        # NL expansion
        try:
            nl = dsl_to_nl(dsl, test_case.get("type", "coder"))
            result["nl_expansion"] = nl
        except Exception as e:
            result["nl_expansion"] = f"Translation error: {e}"

        result["overall_pass"] = (
            result["parses"]
            and len(result["expected_tags_missing"]) == 0
        )

    except DslParseError as e:
        result["parse_error"] = str(e)
    except Exception as e:
        result["parse_error"] = f"Unexpected: {e}"

    return result


def _collect_all_tags(node, tags=None) -> set:
    if tags is None:
        tags = set()
    if hasattr(node, "tag") and node.tag and not node.tag.startswith("_"):
        tags.add(node.tag)
    if hasattr(node, "children"):
        for child in node.children:
            _collect_all_tags(child, tags)
    return tags


# ── Test Runner ──

def run_dry_run(tasks):
    """Print prompts without calling LLM."""
    print("=" * 60)
    print("DSL COMPLIANCE TEST — DRY RUN")
    print("=" * 60)

    for task in tasks:
        print(f"\n{'─' * 50}")
        print(f"Task: {task['name']} ({task['id']})")
        print(f"Type: {task['type']}")
        print(f"Expected tags: {task.get('expected_tags', [])}")
        print(f"\n--- USER PROMPT ---")
        print(task["prompt"])
        print(f"\n--- SYSTEM PROMPT (appended) ---")
        print(DSL_SYSTEM_PROMPT[:300] + "...")
        print()


def run_compliance_test(tasks, agent="pi", model="", verbose=False, output_path=None):
    """Run compliance test with a CLI agent."""
    print("=" * 60)
    print(f"DSL COMPLIANCE TEST — {agent} CLI")
    if model:
        print(f"Model: {model}")
    print("=" * 60)

    results = []
    for i, task in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] {task['name']}")
        print(f"  Type: {task['type']}")

        raw_output, success = call_cli_agent(
            DSL_SYSTEM_PROMPT,
            task["prompt"],
            agent=agent,
            model=model,
        )

        if not success:
            print(f"  LLM call failed: {raw_output[:100]}")
            results.append({
                "test_id": task["id"],
                "name": task["name"],
                "error": raw_output,
                "overall_pass": False,
            })
            continue

        if verbose:
            print(f"  Raw output:\n{raw_output[:400]}")

        validation = validate_output(raw_output, task, verbose)
        results.append(validation)

        status = "PASS" if validation["overall_pass"] else "FAIL"
        print(f"  Has DSL: {validation['has_dsl']}")
        print(f"  Parses: {validation['parses']}")
        if validation["parse_error"]:
            print(f"  Parse error: {validation['parse_error'][:100]}")
        print(f"  Tags found: {validation['expected_tags_found']}")
        if validation["expected_tags_missing"]:
            print(f"  Tags missing: {validation['expected_tags_missing']}")
        if validation.get("nl_expansion"):
            print(f"  NL: {validation['nl_expansion'][:120]}...")
        print(f"  >> {status}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if r.get("overall_pass", False))
    total = len(results)
    print(f"Passed: {passed}/{total}\n")
    for r in results:
        status = "PASS" if r.get("overall_pass") else "FAIL"
        name = r.get("name", r.get("test_id", "unknown"))
        print(f"  {status} — {name}")
        if r.get("parse_error"):
            print(f"         Error: {r['parse_error'][:80]}")
        if r.get("expected_tags_missing"):
            print(f"         Missing: {r['expected_tags_missing']}")

    # Save results
    if output_path:
        output = {
            "timestamp": datetime.now().isoformat(),
            "model": model or "default",
            "passed": passed,
            "total": total,
            "results": [
                {k: v for k, v in r.items() if k != "raw_output"}
                for r in results
            ],
        }
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to {output_path}")

    return results


# ── Main ──

def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM Compliance Test via Claude CLI")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print prompts without calling LLM")
    parser.add_argument("--task", type=str, default=None,
                        help="Run a single task by ID")
    parser.add_argument("--agent", type=str, default="pi",
                        choices=["pi", "claude"],
                        help="CLI agent to use (default: pi)")
    parser.add_argument("--model", type=str, default="",
                        help="Model to use")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show raw LLM output")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Save results to JSON file")
    args = parser.parse_args()

    tasks = TEST_TASKS
    if args.task:
        tasks = [t for t in TEST_TASKS if t["id"] == args.task]
        if not tasks:
            print(f"Unknown task: {args.task}")
            print(f"Available: {[t['id'] for t in TEST_TASKS]}")
            sys.exit(1)

    if args.dry_run:
        run_dry_run(tasks)
    else:
        results = run_compliance_test(
            tasks,
            agent=args.agent,
            model=args.model,
            verbose=args.verbose,
            output_path=args.output,
        )
        passed = sum(1 for r in results if r.get("overall_pass", False))
        sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()

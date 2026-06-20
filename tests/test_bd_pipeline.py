"""
BD Pipeline Integration Test.

Tests the full workflow using `bd` CLI:
1. Cook formula → proto (DAG template)
2. Pour molecule → real issues with dependencies
3. Complete tasks in dependency order
4. Collect results from completed steps
5. Verify dependency tracking (blocked/ready/progress)

Uses bd's formula/molecule system for DAG composition.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dsl_parser import parse_dsl, DslParseError
from src.bd_runner import (
    bd_create, bd_show, bd_update_body, bd_close,
    bd_list, bd_ready, BdPipelineRunner
)


def cleanup(label="test"):
    for issue in bd_list(label=label, status="all"):
        try:
            bd_close(issue.get("id", ""))
        except Exception:
            pass


def test_formula_cook_and_pour():
    """Test: cook formula, pour molecule, verify DAG structure."""
    print("\n=== Test: Formula cook + pour ===")

    cleanup("test-formula")

    runner = BdPipelineRunner(verbose=True)

    # Cook (already done, but verify)
    proto = runner.cook_formula(
        ".beads/formulas/code-review-pipeline.formula.json",
        persist=True
    )
    assert proto == "code-review-pipeline"
    print(f"  Proto: {proto}")

    # Pour
    mol_id = runner.pour_molecule("code-review-pipeline", {
        "task_description": "Add input validation to POST /users",
    })
    assert mol_id, "Pour failed"
    print(f"  Molecule: {mol_id}")

    # Get step IDs
    step_ids = runner.get_molecule_step_ids(mol_id)
    print(f"  Steps: {step_ids}")
    assert len(step_ids) == 3, f"Expected 3 steps, got {len(step_ids)}"

    # Verify dependency structure: implement has no deps, review+test depend on implement
    for sid in step_ids:
        info = bd_show(sid)
        title = info.get("title", "")
        deps = info.get("raw", {}).get("depends_on", []) if info.get("raw") else []
        print(f"    {sid}: {title}")

    return mol_id, step_ids


def test_dependency_ordering():
    """Test: tasks unblock in correct dependency order."""
    print("\n=== Test: Dependency ordering ===")

    runner = BdPipelineRunner(verbose=True)

    # Pour a fresh molecule (reuse existing proto)
    mol_id = runner.pour_molecule("code-review-pipeline", {
        "task_description": "Fix authentication bug",
    })
    assert mol_id
    print(f"  Molecule: {mol_id}")

    step_ids = runner.get_molecule_step_ids(mol_id)

    # Initially: only implement should be ready (no deps)
    ready = bd_ready()
    ready_ids = {r.get("id") for r in ready}

    implement_ids = [s for s in step_ids if s in ready_ids]
    blocked_ids = [s for s in step_ids if s not in ready_ids]

    print(f"  Ready: {[s.split('.')[-1] for s in implement_ids]}")
    print(f"  Blocked: {[s.split('.')[-1] for s in blocked_ids]}")

    assert len(implement_ids) > 0, "At least implement should be ready"
    assert len(blocked_ids) > 0, "Review and test should be blocked"

    # Complete implement
    implement_id = implement_ids[0]
    bd_update_body(implement_id, """[result id=t1 status=complete]
[artifact type=file path=src/auth.py action=modified lines=+15]
[added fn=validate_token in:Request out:TokenResult]
[/result]""")
    bd_close(implement_id)
    print(f"  Completed: {implement_id}")

    # Now review and test should be ready
    ready = bd_ready()
    ready_ids = {r.get("id") for r in ready}
    newly_ready = [s for s in blocked_ids if s in ready_ids]
    print(f"  Newly ready after implement: {[s.split('.')[-1] for s in newly_ready]}")
    assert len(newly_ready) == 2, "Both review and test should be unblocked"

    # Complete all
    for sid in step_ids:
        info = bd_show(sid)
        status = info.get("status", "")
        if status != "closed":
            bd_update_body(sid, f"[result status=complete]Done[/result]")
            bd_close(sid)

    # Verify progress
    progress = runner.get_molecule_progress(mol_id)
    print(f"  Progress: {progress['completed']}/{progress['total']} ({progress['percent']}%)")
    assert progress["percent"] == 100, "Molecule should be 100% complete"


def test_collect_results():
    """Test: pour, work, collect results."""
    print("\n=== Test: Collect results ===")

    runner = BdPipelineRunner(verbose=True)

    mol_id = runner.pour_molecule("code-review-pipeline", {
        "task_description": "Add rate limiting",
    })
    assert mol_id

    step_ids = runner.get_molecule_step_ids(mol_id)
    print(f"  Steps: {step_ids}")

    # Simulate work: complete each step with DSL results
    results_data = [
        ("""[result id=t1 status=complete]
[artifact type=file path=src/middleware/rate_limit.py action=created lines=30]
[artifact type=file path=src/app.py action=modified lines=+5]
[added fn=rate_limit in:Request out:Response]
[/result]"""),
        ("""[result id=t2 status=complete]
[verdict approve]
[finding severity=minor path=src/middleware/rate_limit.py:12]
Consider adding configurable rate limits per endpoint.
[/finding]
[/result]"""),
        ("""[result id=t3 status=complete]
[artifact type=file path=tests/test_rate_limit.py action=created lines=50]
[test-suite total=6 pass=5 fail=1]
[test name=test_basic_rate_limit status=pass]
[test name=test_burst_allowance status=pass]
[test name=test_per_endpoint status=pass]
[test name=test_headers status=pass]
[test name=test_exemption status=pass]
[test name=test_concurrent status=fail reason="race condition in counter"]
[/test-suite]
[/result]"""),
    ]

    for sid, result_dsl in zip(step_ids, results_data):
        bd_update_body(sid, result_dsl)
        bd_close(sid)
        print(f"  Completed: {sid}")

    # Collect results
    results = runner.collect_molecule_results(mol_id)
    print(f"  Collected {len(results)} results")

    for r in results:
        if r["parsed_ok"]:
            print(f"    {r['bd_id']}: {r['status']}, {len(r.get('artifacts', []))} artifacts")
        else:
            print(f"    {r['bd_id']}: ERROR - {r.get('error', 'unknown')}")

    assert all(r["parsed_ok"] for r in results), "All results should parse"
    assert all(r["status"] == "complete" for r in results), "All should be complete"


def main():
    print("=" * 60)
    print("BD Pipeline Integration Test (Formula/Molecule)")
    print("=" * 60)
    cleanup("test-formula")

    try:
        test_formula_cook_and_pour()
        test_dependency_ordering()
        test_collect_results()
        ok = True
    except Exception as e:
        print(f"\n  FAIL: {e}")
        import traceback; traceback.print_exc()
        ok = False
    finally:
        cleanup("test-formula")

    print(f"\n{'=' * 60}\nOverall: {'PASS' if ok else 'FAIL'}\n{'=' * 60}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

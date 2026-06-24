#!/usr/bin/env python3
"""Static quality sensor for test files.

Detects poor-quality tests that are likely to mislead rather than protect:
- Tests with no assertions (always pass, prove nothing)
- Trivially true assertions (assert True, assert 1)
- Sole assertion is 'assert result is not None' (proves existence, not behaviour)
- Generic non-descriptive names (test_1, test_it, test_func)
- Empty test bodies (pass or ...)

Usage (from project root):
    python <skill-path>/scripts/lint_tests.py <file_or_dir> [<file_or_dir> ...]

Exit codes:
    0 — no critical or major findings
    1 — one or more critical or major findings
    2 — usage error or unrecoverable parse failure
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


CRIT = "crit"
MAJOR = "major"
INFO = "info"

MAX_LINES = 60

GENERIC_NAMES = {
    "test_it", "test_this", "test_func", "test_function", "test_method",
    "test_1", "test_2", "test_3", "test_4", "test_5",
    "test_thing", "test_test", "test_me", "test_foo", "test_bar", "test_baz",
    "test_stuff", "test_something", "test_works", "test_ok",
}


@dataclass
class Finding:
    sev: str
    path: str
    line: int
    name: str
    message: str


def _asserts(func: ast.FunctionDef) -> list[ast.Assert]:
    return [n for n in ast.walk(func) if isinstance(n, ast.Assert)]


def _is_trivially_true(node: ast.Assert) -> bool:
    t = node.test
    return isinstance(t, ast.Constant) and bool(t.value)


def _is_not_none_only(asserts: list[ast.Assert]) -> bool:
    if len(asserts) != 1:
        return False
    t = asserts[0].test
    if not isinstance(t, ast.Compare):
        return False
    return (
        len(t.ops) == 1
        and isinstance(t.ops[0], ast.IsNot)
        and len(t.comparators) == 1
        and isinstance(t.comparators[0], ast.Constant)
        and t.comparators[0].value is None
    )


def _is_empty(func: ast.FunctionDef) -> bool:
    # Strip leading docstring
    stmts = func.body[:]
    if stmts and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant) and isinstance(stmts[0].value.value, str):
        stmts = stmts[1:]
    if not stmts:
        return True
    if len(stmts) == 1:
        s = stmts[0]
        if isinstance(s, ast.Pass):
            return True
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is ...:
            return True
    return False


def _is_generic(name: str) -> bool:
    if name in GENERIC_NAMES:
        return True
    suffix = name[5:] if name.startswith("test_") else name
    return len(suffix) <= 2


def check_file(path: Path) -> tuple[list[Finding], bool]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        print(f"PARSE ERROR  {path}:{e.lineno}  {e.msg}", file=sys.stderr)
        return [], True
    except OSError as e:
        print(f"READ ERROR  {path}  {e}", file=sys.stderr)
        return [], True

    findings: list[Finding] = []
    rel = str(path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        name = node.name
        if not name.startswith("test_"):
            continue

        if _is_empty(node):
            findings.append(Finding(CRIT, rel, node.lineno, name, "empty body — no behaviour tested"))
            continue

        asserts = _asserts(node)

        if not asserts:
            findings.append(Finding(CRIT, rel, node.lineno, name, "no assertions — test always passes, proves nothing"))
            continue

        trivial = [a for a in asserts if _is_trivially_true(a)]
        if trivial:
            findings.append(Finding(CRIT, rel, trivial[0].lineno, name, "trivially true assertion (assert True / assert 1)"))

        if _is_not_none_only(asserts):
            findings.append(Finding(MAJOR, rel, node.lineno, name, "sole assertion is 'assert result is not None' — verifies existence, not behaviour"))

        if _is_generic(name):
            findings.append(Finding(MAJOR, rel, node.lineno, name, f"name '{name}' is too generic — use test_<what>_<condition>_<expected>"))

        end = getattr(node, "end_lineno", None) or node.lineno
        length = end - node.lineno
        if length > MAX_LINES:
            findings.append(Finding(INFO, rel, node.lineno, name, f"{length} lines — likely testing multiple behaviours; split into focused tests"))

    return findings, False


def collect_files(paths: list[str]) -> list[Path]:
    found: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found.update(p.rglob("test_*.py"))
            found.update(p.rglob("*_test.py"))
        elif p.is_file() and p.suffix == ".py":
            found.add(p)
    return sorted(found)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: lint_tests.py <file_or_dir> [...]", file=sys.stderr)
        sys.exit(2)

    files = collect_files(sys.argv[1:])
    if not files:
        print("No test files found.")
        sys.exit(0)

    all_findings: list[Finding] = []
    parse_errors = 0
    _order = {CRIT: 0, MAJOR: 1, INFO: 2}

    for f in files:
        findings, err = check_file(f)
        all_findings.extend(findings)
        if err:
            parse_errors += 1

    all_findings.sort(key=lambda f: (_order[f.sev], f.path, f.line))

    for f in all_findings:
        print(f"{f.sev.upper():<6}  {f.path}:{f.line}  [{f.name}]  {f.message}")

    n_crit = sum(1 for f in all_findings if f.sev == CRIT)
    n_major = sum(1 for f in all_findings if f.sev == MAJOR)
    n_info = sum(1 for f in all_findings if f.sev == INFO)

    suffix = f"  |  {parse_errors} parse error(s)" if parse_errors else ""
    print(f"\n{len(files)} file(s) scanned  |  {n_crit} crit  |  {n_major} major  |  {n_info} info{suffix}")

    sys.exit(1 if (n_crit or n_major) else 0)


if __name__ == "__main__":
    main()

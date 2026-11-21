#!/usr/bin/env python3
# [origin ref=llm-dsl-5ygq req=REQ-OPERATOR-EDU-011 c4=sdd_skills/arch_review]
#   [intent]Static test-quality sensor for Python (AST) and TypeScript/JavaScript (Vitest/Jest, brace-matching scanner) test files, reporting crit/major/info findings with exit codes for arch-review.[/intent]
# [/origin]
"""Static quality sensor for test files.

Detects poor-quality tests that are likely to mislead rather than protect:
- Tests with no assertions (always pass, prove nothing)
- Trivially true assertions (assert True, assert 1, expect(true), expect(1))
- Sole assertion is 'assert result is not None' / expect(x).toBeDefined() (proves existence, not behaviour)
- Generic non-descriptive names (test_1, test_it, test_func, 'works', 'test 1')
- Empty test bodies (pass or ..., {})

Python files: test_*.py, *_test.py (AST based).
TypeScript/JavaScript files: *.test.ts, *.test.js, *.test.mjs, *.spec.ts
(it/test/describe-free scan; it.each and test.each supported; skip/todo ignored).

Usage (from project root):
    python <skill-path>/scripts/lint_tests.py <file_or_dir> [<file_or_dir> ...]

Exit codes:
    0 — no critical or major findings
    1 — one or more critical or major findings
    2 — usage error or unrecoverable parse failure
"""

import ast
import re
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

TS_SUFFIXES = (".test.ts", ".test.js", ".test.mjs", ".spec.ts")
TS_SKIP_DIRS = {"node_modules", ".git"}
TS_WEAK_MATCHERS = {(False, "toBeDefined"), (False, "toBeTruthy"), (True, "toBeUndefined")}
TS_GENERIC = re.compile(
    r"^(?:(?:it|test|should)\s+)?(?:works?|ok|it|test(?:\s*\d+)?|this|func(?:tion)?|thing|stuff|something|foo|bar|baz|me|\d+)$"
)
TS_TEST_HEAD = re.compile(r"(?<![\w$.])(it|test)(?![\w$])((?:\s*\.\s*[A-Za-z_$][\w$]*)*)")
TS_ASSERT_CALL = re.compile(r"(?<![\w$])((?:expect|assert)\w*)\s*\(")
TS_WEAK_TAIL = re.compile(r"\s*\.\s*(not\s*\.\s*)?([A-Za-z_]\w*)\s*\(\s*\)")
TS_BARE = re.compile(r"^[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)*$")
TS_TRIVIAL = re.compile(r"^(?:true|\d+(?:\.\d+)?)$")
TS_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
TS_WORD_RUN = re.compile(r"[\w$]*")
TS_REGEX_AFTER_WORDS = {
    "return", "typeof", "case", "do", "else", "in", "of", "yield", "await", "void", "delete", "throw", "new",
}
TS_REGEX_AFTER_CHARS = set("(,=:[!&|?{};+-*%<>~^")
CLOSER = {"(": ")", "[": "]", "{": "}"}


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


def _is_ts_test(p: Path) -> bool:
    return p.name.endswith(TS_SUFFIXES) and not TS_SKIP_DIRS.intersection(p.parts)


def _mask_ts(src: str) -> str:
    out = list(src)
    n = len(src)

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    def tmpl(j: int) -> tuple[int, bool]:
        k = j
        while k < n:
            ch = src[k]
            if ch == "\\":
                k += 2
                continue
            if ch == "`":
                blank(j, k)
                return k + 1, False
            if ch == "$" and k + 1 < n and src[k + 1] == "{":
                blank(j, k)
                return k + 2, True
            k += 1
        blank(j, n)
        return n, False

    i = 0
    depth = 0
    open_exprs: list[int] = []
    prev = ""
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            j = min(j, n)
            blank(i + 1, j)
            i = j + 1
            prev = "0"
            continue
        if c == "`":
            i, expr = tmpl(i + 1)
            if expr:
                open_exprs.append(depth)
            prev = "0"
            continue
        if c == "/" and (prev == "" or prev in TS_REGEX_AFTER_CHARS or prev in TS_REGEX_AFTER_WORDS):
            j = i + 1
            in_class = False
            while j < n and src[j] != "\n":
                ch = src[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    break
                j += 1
            j = min(j, n)
            blank(i + 1, j)
            i = TS_WORD_RUN.match(src, min(j + 1, n)).end()
            prev = "0"
            continue
        if c.isalpha() or c in "_$":
            j = TS_WORD_RUN.match(src, i).end()
            prev = src[i:j]
            i = j
            continue
        if c.isdigit():
            i = TS_WORD_RUN.match(src, i).end()
            prev = "0"
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if open_exprs and depth == open_exprs[-1]:
                open_exprs.pop()
                i, expr = tmpl(i + 1)
                if expr:
                    open_exprs.append(depth)
                prev = "0"
                continue
            depth -= 1
        prev = c
        i += 1
    return "".join(out)


def _balanced(masked: str) -> bool:
    stack: list[str] = []
    for ch in masked:
        if ch in CLOSER:
            stack.append(CLOSER[ch])
        elif ch in ")]}":
            if not stack or stack.pop() != ch:
                return False
    return not stack


def _close_at(masked: str, j: int) -> int:
    stack: list[str] = []
    for k in range(j, len(masked)):
        ch = masked[k]
        if ch in CLOSER:
            stack.append(CLOSER[ch])
        elif ch in ")]}":
            if not stack or stack.pop() != ch:
                return -1
            if not stack:
                return k
    return -1


def _skip_ws(s: str, j: int) -> int:
    while j < len(s) and s[j].isspace():
        j += 1
    return j


def _split_args(masked: str, a: int, b: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    depth = 0
    start = a
    for k in range(a, b):
        ch = masked[k]
        if ch in CLOSER:
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            spans.append((start, k))
            start = k + 1
    spans.append((start, b))
    return [(s, e) for s, e in spans if masked[s:e].strip()]


def _fn_body(masked: str, a: int, b: int) -> tuple[int, int] | None:
    j = _skip_ws(masked, a)
    m = TS_IDENT.match(masked, j)
    if m and m.group() == "async":
        j = _skip_ws(masked, m.end())
    if masked.startswith("function", j):
        j = _skip_ws(masked, j + 8)
        if masked[j:j + 1] == "*":
            j = _skip_ws(masked, j + 1)
        m = TS_IDENT.match(masked, j)
        if m:
            j = _skip_ws(masked, m.end())
        if masked[j:j + 1] != "(":
            return None
        close = _close_at(masked, j)
        if close < 0:
            return None
        j = _skip_ws(masked, close + 1)
        if masked[j:j + 1] != "{":
            return None
        end = _close_at(masked, j)
        return None if end < 0 else (j + 1, end)
    if masked[j:j + 1] == "(":
        close = _close_at(masked, j)
        if close < 0:
            return None
        j = close + 1
    else:
        m = TS_IDENT.match(masked, j)
        if not m:
            return None
        j = m.end()
    j = _skip_ws(masked, j)
    if not masked.startswith("=>", j):
        return None
    j = _skip_ws(masked, j + 2)
    if masked[j:j + 1] == "{":
        end = _close_at(masked, j)
        return None if end < 0 else (j + 1, end)
    return (j, b)


def _ts_call(masked: str, m: re.Match[str]) -> tuple[tuple[int, int], tuple[int, int], int] | None:
    words = re.findall(r"\.\s*([A-Za-z_$][\w$]*)", m.group(2))
    if any(w == "todo" or w.startswith("skip") for w in words):
        return None
    need_table = "each" in words
    j = m.end()
    while True:
        j = _skip_ws(masked, j)
        ch = masked[j:j + 1]
        if ch == "(":
            close = _close_at(masked, j)
            if close < 0:
                return None
            if need_table:
                need_table = False
                j = close + 1
                continue
            spans = _split_args(masked, j + 1, close)
            if len(spans) < 2:
                return None
            return spans[0], spans[1], close
        if ch == "`" and need_table:
            end = masked.find("`", j + 1)
            if end < 0:
                return None
            need_table = False
            j = end + 1
            continue
        return None


def _ts_title(src: str, span: tuple[int, int]) -> str:
    raw = src[span[0]:span[1]].strip()
    if len(raw) >= 2 and raw[0] in "'\"`" and raw[-1] == raw[0]:
        return raw[1:-1]
    return raw


def _ts_generic(name: str) -> bool:
    norm = re.sub(r"\s+", " ", name.strip().lower()).rstrip(".!")
    return len(norm) <= 2 or TS_GENERIC.match(norm) is not None


def _line(masked: str, off: int) -> int:
    return masked.count("\n", 0, off) + 1


def check_ts_file(path: Path) -> tuple[list[Finding], bool]:
    try:
        src = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"READ ERROR  {path}  {e}", file=sys.stderr)
        return [], True

    masked = _mask_ts(src)
    if not _balanced(masked):
        print(f"PARSE ERROR  {path}  unbalanced brackets", file=sys.stderr)
        return [], True

    rel = str(path)
    findings: list[Finding] = []

    for m in TS_TEST_HEAD.finditer(masked):
        call = _ts_call(masked, m)
        if call is None:
            continue
        name_span, cb, close = call
        name = _ts_title(src, name_span)
        line = _line(masked, m.start())
        body = _fn_body(masked, *cb)
        if body is None:
            continue
        bs, be = body
        text = masked[bs:be]

        if not text.strip():
            findings.append(Finding(CRIT, rel, line, name, "empty body — no behaviour tested"))
            continue

        calls = list(TS_ASSERT_CALL.finditer(text))
        if not calls:
            findings.append(Finding(CRIT, rel, line, name, "no assertions — test always passes, proves nothing"))
            continue

        for c in calls:
            q = c.end() - 1
            end = _close_at(text, q)
            if end >= 0 and TS_TRIVIAL.match(text[q + 1:end].strip()):
                findings.append(Finding(CRIT, rel, _line(masked, bs + c.start()), name, "trivially true assertion (expect(true) / expect(1))"))
                break

        if len(calls) == 1 and calls[0].group(1) == "expect":
            q = calls[0].end() - 1
            end = _close_at(text, q)
            if end >= 0:
                arg = text[q + 1:end].strip()
                tail = TS_WEAK_TAIL.match(text, end + 1)
                if tail and TS_BARE.match(arg) and (tail.group(1) is not None, tail.group(2)) in TS_WEAK_MATCHERS:
                    findings.append(Finding(MAJOR, rel, line, name, f"sole assertion is '.{tail.group(2)}()' on a bare value — verifies existence, not behaviour"))

        if _ts_generic(name):
            findings.append(Finding(MAJOR, rel, line, name, f"name '{name}' is too generic — describe the behaviour and condition"))

        length = _line(masked, close) - line
        if length > MAX_LINES:
            findings.append(Finding(INFO, rel, line, name, f"{length} lines — likely testing multiple behaviours; split into focused tests"))

    return findings, False


def check_file(path: Path) -> tuple[list[Finding], bool]:
    if _is_ts_test(path):
        return check_ts_file(path)
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
            for suffix in TS_SUFFIXES:
                for f in p.rglob(f"*{suffix}"):
                    if not TS_SKIP_DIRS.intersection(f.relative_to(p).parts):
                        found.add(f)
        elif p.is_file() and (p.suffix == ".py" or _is_ts_test(p)):
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

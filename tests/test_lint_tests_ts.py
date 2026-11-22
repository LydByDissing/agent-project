# [origin ref=llm-dsl-5ygq req=REQ-OPERATOR-EDU-011 c4=sdd_skills/arch_review]
#   [intent]Tests the TypeScript/JavaScript path of the arch-review lint_tests.py sensor: each finding class, clean files, brace-safe scanning, it.each, helper assertions and CLI exit codes.[/intent]
# [/origin]

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "arch-review" / "scripts" / "lint_tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("lint_tests", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lt = _load()


def _check(tmp_path: Path, src: str, name: str = "sample.test.ts"):
    p = tmp_path / name
    p.write_text(src, encoding="utf-8")
    findings, err = lt.check_file(p)
    assert not err
    return [(f.sev, f.name, f.message) for f in findings]


def _cli(*args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
    )


def test_no_assertion_is_crit(tmp_path):
    src = "it('adds numbers', () => {\n  const x = 1 + 1;\n});\n"
    got = _check(tmp_path, src)
    assert [(s, n) for s, n, _ in got] == [("crit", "adds numbers")]
    assert "no assertions" in got[0][2]


def test_empty_body_is_crit(tmp_path):
    src = "it('nothing', () => {});\n"
    got = _check(tmp_path, src)
    assert got[0][0] == "crit" and got[0][1] == "nothing"
    assert "empty body" in got[0][2]


def test_comment_only_body_is_empty(tmp_path):
    src = "test('later', () => {\n  // TODO write this\n});\n"
    got = _check(tmp_path, src)
    assert len(got) == 1 and "empty body" in got[0][2]


def test_expect_true_is_trivially_true(tmp_path):
    src = "it('always', () => {\n  expect(true).toBe(true);\n});\n"
    got = _check(tmp_path, src)
    assert ("crit", "always") in [(s, n) for s, n, _ in got]
    assert any("trivially true" in m for _, _, m in got)


def test_expect_numeric_literal_is_trivially_true(tmp_path):
    src = "it('one', () => {\n  expect(1);\n});\n"
    got = _check(tmp_path, src)
    assert got and got[0][0] == "crit" and "trivially true" in got[0][2]


def test_sole_to_be_defined_is_major(tmp_path):
    src = "it('has a value', () => {\n  const r = make();\n  expect(r).toBeDefined();\n});\n"
    got = _check(tmp_path, src)
    assert len(got) == 1 and got[0][0] == "major" and "toBeDefined" in got[0][2]


def test_sole_not_to_be_undefined_is_major(tmp_path):
    src = "it('is set', () => {\n  expect(store.value).not.toBeUndefined();\n});\n"
    got = _check(tmp_path, src)
    assert len(got) == 1 and got[0][0] == "major" and "toBeUndefined" in got[0][2]


def test_sole_to_be_truthy_on_bare_value_is_major(tmp_path):
    src = "it('is truthy', () => {\n  expect(res).toBeTruthy();\n});\n"
    got = _check(tmp_path, src)
    assert len(got) == 1 and got[0][0] == "major"


def test_truthy_on_comparison_is_not_weak(tmp_path):
    src = "it('compares', () => {\n  expect(a === b).toBeTruthy();\n});\n"
    assert _check(tmp_path, src) == []


def test_weak_matcher_with_other_assertion_is_not_major(tmp_path):
    src = "it('both', () => {\n  expect(r).toBeDefined();\n  expect(r.id).toBe(3);\n});\n"
    assert _check(tmp_path, src) == []


@pytest.mark.parametrize("title", ["works", "test 1", "it works", "ok", "it", "test"])
def test_generic_names_are_major(tmp_path, title):
    src = f"it('{title}', () => {{\n  expect(f()).toBe(2);\n}});\n"
    got = _check(tmp_path, src)
    assert got == [("major", title, f"name '{title}' is too generic — describe the behaviour and condition")]


def test_descriptive_name_is_not_generic(tmp_path):
    src = "it('returns the sum of two numbers', () => {\n  expect(add(1, 2)).toBe(3);\n});\n"
    assert _check(tmp_path, src) == []


def test_skip_and_todo_are_ignored(tmp_path):
    src = (
        "it.skip('later', () => {});\n"
        "it.todo('not written');\n"
        "test.skip('also later', () => { const x = 1; });\n"
        "it.skipIf(cond)('x', () => {});\n"
    )
    assert _check(tmp_path, src) == []


def test_it_each_clean_and_empty(tmp_path):
    clean = (
        "it.each([[1, 2, 3], [2, 2, 4]])('adds %i and %i', (a, b, sum) => {\n"
        "  expect(a + b).toBe(sum);\n"
        "});\n"
    )
    assert _check(tmp_path, clean) == []

    bad = "test.each([[1], [2]])('does %i', (a) => {});\n"
    got = _check(tmp_path, bad, name="each.test.ts")
    assert got == [("crit", "does %i", "empty body — no behaviour tested")]


def test_it_each_without_assertion_is_crit(tmp_path):
    src = "it.each`\n  a  | b\n  ${1} | ${2}\n`('pairs $a', ({ a, b }) => {\n  const s = a + b;\n});\n"
    got = _check(tmp_path, src)
    assert got == [("crit", "pairs $a", "no assertions — test always passes, proves nothing")]


def test_helper_assert_call_counts_as_assertion(tmp_path):
    src = (
        "function expectIssue(x, code) {\n"
        "  expect(x.code).toBe(code);\n"
        "}\n"
        "function assertClean(x) {\n"
        "  expect(x.length).toBe(0);\n"
        "}\n"
        "it('flags a bad row', () => {\n"
        "  expectIssue(run('bad'), 'E1');\n"
        "});\n"
        "it('is clean', () => {\n"
        "  assertClean(run('good'));\n"
        "});\n"
    )
    assert _check(tmp_path, src) == []


def test_non_assert_helper_is_not_an_assertion(tmp_path):
    src = "it('checks', () => {\n  verifyIssue(run('bad'));\n});\n"
    got = _check(tmp_path, src)
    assert [(s, n) for s, n, _ in got] == [("crit", "checks")]


def test_braces_in_strings_templates_and_comments_are_masked(tmp_path):
    src = (
        "it('braces are inert', () => {\n"
        "  const s = \"}{ ) ]\";\n"
        "  const t = `}` + `${ {a: 1}.a }` + `{`;\n"
        "  // } } } it('ghost', () => {\n"
        "  /* { ( [ */\n"
        "  const fake = 'it(\"x\", () => {';\n"
        "  const re = /[{}]\\/}/;\n"
        "  expect(s).toBe(\"}{ ) ]\");\n"
        "});\n"
        "it('after', () => {\n"
        "  expect(t.length).toBeGreaterThan(0);\n"
        "});\n"
    )
    assert _check(tmp_path, src) == []


def test_template_expression_braces_do_not_end_body_early(tmp_path):
    src = (
        "it('nested template', () => {\n"
        "  const v = `a ${ [1].map((x) => { return x; }) } b`;\n"
        "  expect(v).toContain('a');\n"
        "});\n"
    )
    assert _check(tmp_path, src) == []


def test_unbalanced_file_is_parse_error(tmp_path, capsys):
    p = tmp_path / "broken.test.ts"
    p.write_text("it('x', () => {\n  expect(1).toBe(1);\n", encoding="utf-8")
    findings, err = lt.check_file(p)
    assert findings == [] and err is True
    assert "PARSE ERROR" in capsys.readouterr().err


def test_clean_file_has_no_findings(tmp_path):
    src = (
        "import { describe, expect, it } from 'vitest';\n"
        "import { parse } from '../src/parse.js';\n"
        "describe('parse', () => {\n"
        "  it('returns the id of a record', () => {\n"
        "    const r = parse('{\"id\": 7}');\n"
        "    expect(r.id).toBe(7);\n"
        "  });\n"
        "  it('rejects a missing id', () => {\n"
        "    expect(() => parse('{}')).toThrow(/missing id/);\n"
        "  });\n"
        "  it('keeps unknown fields', async () => {\n"
        "    const r = await Promise.resolve(parse('{\"id\": 1, \"x\": 2}'));\n"
        "    expect(r).toMatchObject({ x: 2 });\n"
        "  });\n"
        "});\n"
    )
    assert _check(tmp_path, src) == []


def test_long_test_is_info_only(tmp_path):
    body = "".join(f"  expect(v{k}).toBe({k});\n" for k in range(70))
    src = "it('does many things', () => {\n" + body + "});\n"
    got = _check(tmp_path, src)
    assert [s for s, _, _ in got] == ["info"]


def test_cli_exit_code_clean(tmp_path):
    p = tmp_path / "ok.test.ts"
    p.write_text("it('returns the sum', () => {\n  expect(1 + 1).toBe(2);\n});\n", encoding="utf-8")
    proc = _cli(p)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 crit  |  0 major  |  0 info" in proc.stdout


def test_cli_exit_code_crit(tmp_path):
    p = tmp_path / "bad.test.ts"
    p.write_text("it('nothing asserted', () => {\n  run();\n});\n", encoding="utf-8")
    proc = _cli(p)
    assert proc.returncode == 1
    assert "CRIT" in proc.stdout and "[nothing asserted]" in proc.stdout


def test_cli_exit_code_major(tmp_path):
    p = tmp_path / "maj.spec.ts"
    p.write_text("it('works', () => {\n  expect(f()).toBeDefined();\n});\n", encoding="utf-8")
    assert _cli(p).returncode == 1


def test_cli_usage_error_exits_2():
    proc = _cli()
    assert proc.returncode == 2
    assert "Usage" in proc.stderr


def test_cli_directory_discovery(tmp_path):
    (tmp_path / "a.test.ts").write_text("it('adds', () => { expect(1).toBe(1); });\n", encoding="utf-8")
    (tmp_path / "b.test.js").write_text("it('b', () => {});\n", encoding="utf-8")
    (tmp_path / "c.test.mjs").write_text("it('c', () => {});\n", encoding="utf-8")
    (tmp_path / "d.spec.ts").write_text("it('d', () => {});\n", encoding="utf-8")
    (tmp_path / "helper.ts").write_text("it('helper', () => {});\n", encoding="utf-8")
    nm = tmp_path / "node_modules" / "dep"
    nm.mkdir(parents=True)
    (nm / "x.test.ts").write_text("it('dep', () => {});\n", encoding="utf-8")
    (tmp_path / "test_py.py").write_text("def test_real():\n    assert 1 == 1\n", encoding="utf-8")

    files = [p.name for p in lt.collect_files([str(tmp_path)])]
    assert files == ["a.test.ts", "b.test.js", "c.test.mjs", "d.spec.ts", "test_py.py"]

    proc = _cli(tmp_path)
    assert proc.returncode == 1
    assert "5 file(s) scanned" in proc.stdout
    assert "[b]" in proc.stdout and "[dep]" not in proc.stdout


def test_python_path_still_reports(tmp_path):
    p = tmp_path / "test_old.py"
    p.write_text("def test_nothing():\n    x = 1\n", encoding="utf-8")
    proc = _cli(p)
    assert proc.returncode == 1
    assert "[test_nothing]" in proc.stdout and "no assertions" in proc.stdout


def test_timeout_argument_does_not_hide_callback(tmp_path):
    src = "it('slow', async () => {\n  const x = 1;\n}, 20_000);\n"
    got = _check(tmp_path, src)
    assert got == [("crit", "slow", "no assertions — test always passes, proves nothing")]


def test_function_expression_callback_is_analysed(tmp_path):
    src = "test('returns three', function ({ a, b }) {\n  expect(a + b).toBe(3);\n});\n"
    assert _check(tmp_path, src) == []
    src = "test('returns three', function () {});\n"
    got = _check(tmp_path, src)
    assert got and got[0][0] == "crit" and "empty body" in got[0][2]

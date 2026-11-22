# [origin ref=llm-dsl-2zv1 req=REQ-SECURITY-REVIEW-013 c4=sdd_skills/arch_review]
#   [intent]Tests the Python path of the arch-review lint_tests.py sensor: which constructs count as assertions (assert, pytest.raises/warns/fail, resolved helpers, assert*/expect* calls, self.assert*) and that tests without any are still crit.[/intent]
# [/origin]

import importlib.util
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


def _check(tmp_path: Path, src: str, name: str = "test_sample.py"):
    p = tmp_path / name
    p.write_text(src, encoding="utf-8")
    findings, err = lt.check_file(p)
    assert not err
    return findings


def _no_assert(findings):
    return [f.name for f in findings if "no assertions" in f.message]


def test_plain_assert_statement_is_an_assertion(tmp_path):
    assert _no_assert(_check(tmp_path, "def test_a_long_name():\n    assert 1 + 1 == 2\n")) == []


def test_test_without_any_assertion_is_crit(tmp_path):
    f = _check(tmp_path, "def test_nothing_checked():\n    x = 1 + 1\n    print(x)\n")
    assert [(x.sev, x.name) for x in f] == [("crit", "test_nothing_checked")]


@pytest.mark.parametrize("body", [
    "    with pytest.raises(ValueError):\n        int('x')\n",
    "    with pytest.warns(UserWarning):\n        pass_it()\n",
    "    pytest.fail('boom')\n",
    "    pytest.raises(ValueError, int, 'x')\n",
])
def test_pytest_constructs_count_as_assertions(tmp_path, body):
    src = "import pytest\n\ndef pass_it():\n    pass\n\ndef test_pytest_construct_checked():\n" + body
    assert _no_assert(_check(tmp_path, src)) == []


def test_other_receiver_named_raises_is_not_an_assertion(tmp_path):
    src = "def test_fake_raises_checked():\n    obj.raises(1)\n    obj.fail('x')\n"
    assert _no_assert(_check(tmp_path, src)) == ["test_fake_raises_checked"]


def test_call_to_asserting_module_helper_counts(tmp_path):
    src = "def ok(x):\n    assert x\n\ndef test_helper_asserts_inside():\n    ok(1)\n"
    assert _no_assert(_check(tmp_path, src)) == []


def test_call_to_non_asserting_helper_is_crit(tmp_path):
    src = "def run(x):\n    return x\n\ndef test_helper_does_not_assert():\n    run(1)\n"
    assert _no_assert(_check(tmp_path, src)) == ["test_helper_does_not_assert"]


def test_helper_resolved_transitively(tmp_path):
    src = (
        "def inner(x):\n    assert x\n\n"
        "def outer(x):\n    inner(x)\n\n"
        "def test_transitive_helper_chain():\n    outer(1)\n"
    )
    assert _no_assert(_check(tmp_path, src)) == []


def test_helper_cycle_terminates_and_is_crit(tmp_path):
    src = (
        "def a():\n    b()\n\n"
        "def b():\n    a()\n\n"
        "def test_cyclic_helpers_never_assert():\n    a()\n"
    )
    assert _no_assert(_check(tmp_path, src)) == ["test_cyclic_helpers_never_assert"]


def test_helper_imported_from_sibling_module_counts(tmp_path):
    (tmp_path / "helpers_mod.py").write_text("def fails(x):\n    assert not x\n", encoding="utf-8")
    src = "from helpers_mod import fails\n\ndef test_imported_helper_asserts():\n    fails(0)\n"
    assert _no_assert(_check(tmp_path, src)) == []


def test_helper_imported_from_missing_module_is_crit(tmp_path):
    src = "from nowhere_mod import fails\n\ndef test_unresolvable_import_helper():\n    fails(0)\n"
    assert _no_assert(_check(tmp_path, src)) == ["test_unresolvable_import_helper"]


def test_imported_helper_that_does_not_assert_is_crit(tmp_path):
    (tmp_path / "helpers_mod.py").write_text("def fails(x):\n    return x\n", encoding="utf-8")
    src = "from helpers_mod import fails\n\ndef test_imported_helper_silent():\n    fails(0)\n"
    assert _no_assert(_check(tmp_path, src)) == ["test_imported_helper_silent"]


@pytest.mark.parametrize("call", ["assert_equal(1, 1)", "assertIssue(x)", "expect(1).to_be(1)", "expectIssue(x)", "lib.assert_ok(x)"])
def test_assert_and_expect_prefixed_calls_count(tmp_path, call):
    src = f"def test_prefixed_call_checked(x=1):\n    {call}\n"
    assert _no_assert(_check(tmp_path, src)) == []


def test_unittest_self_assert_counts(tmp_path):
    src = "import unittest\n\nclass T(unittest.TestCase):\n    def test_unittest_style_checked(self):\n        self.assertEqual(1, 1)\n"
    assert _no_assert(_check(tmp_path, src)) == []


def test_self_helper_method_that_asserts_counts(tmp_path):
    src = "class T:\n    def check(self):\n        assert True is not False\n\n    def test_method_helper_checked(self):\n        self.check()\n"
    assert _no_assert(_check(tmp_path, src)) == []


def test_sole_not_none_assert_still_major_with_no_other_assertion(tmp_path):
    f = _check(tmp_path, "def test_returns_something_useful():\n    r = 1\n    assert r is not None\n")
    assert [(x.sev) for x in f] == ["major"]


def test_not_none_assert_with_raises_is_not_flagged(tmp_path):
    src = "import pytest\n\ndef test_raises_and_not_none_checked():\n    r = 1\n    assert r is not None\n    with pytest.raises(ValueError):\n        int('x')\n"
    assert _check(tmp_path, src) == []


def test_trivially_true_assert_still_crit(tmp_path):
    f = _check(tmp_path, "def test_trivial_assertion_here():\n    assert True\n")
    assert [x.sev for x in f] == ["crit"]


def test_existing_ts_tests_still_pass():
    import subprocess, sys
    r = subprocess.run([sys.executable, "-m", "pytest", str(ROOT / "tests" / "test_lint_tests_ts.py"), "-q"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-500:]

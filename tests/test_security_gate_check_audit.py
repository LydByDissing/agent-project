# [origin ref=llm-dsl-2zv1.4 req=REQ-SECURITY-REVIEW-008,REQ-SECURITY-REVIEW-011 c4=sdd_skills/security_review]
#   [intent]Audits security_gate.py check with end-to-end attack scenarios on real temp git repos, each of which must make the check fail for the named cause.[/intent]
# [/origin]

import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_security_gate_check import EPIC, FEAT, GATE, RUN, SCRIPTS, SPEC, Repo, add_design, design_repo, post_repo, row, table, threat

REV = "docs/source/security/reviews.rst"
SEC = "docs/source/security/**=accepted"
TM = "docs/source/security/threat-model/my-box.rst"


def chk(r, stage, base, **kw):
    res = r.check(stage, base, **kw)
    assert len(r.git("worktree", "list").splitlines()) == 1, r.git("worktree", "list")
    return res


def fails(res, *texts):
    rc, out, err = res
    assert rc == 1, (rc, out, err)
    for t in texts:
        assert t in err, (t, err)


def ok(res):
    assert res[0] == 0, res


def post_with(tmp_path, name, path, listed, body="x\n"):
    r = add_design(design_repo(tmp_path, name))
    design = row("design", r.base, r.base, r.tree())
    r.w(path, body)
    i1 = r.commit("implement")
    r.w(TM, threat("mitigated", decided=True))
    rows = [design, row("post", r.base, i1, r.tree(), f"{SEC} {listed}".replace(" -", ""), "2")]
    r.w(REV, table(rows))
    r.i1 = i1
    r.commit("post gate")
    return r


def script_repo(tmp_path, name):
    r = Repo(tmp_path / name)
    r.w("docs/source/specs/features/f.rst", SPEC)
    r.w(TM, threat())
    r.w(REV, table([]))
    r.w("scripts/security_gate.py", GATE.read_text())
    shutil.copy(SCRIPTS / "security_gate_lib.py", r.p / "scripts")
    r.commit("c0 with script")
    r.git("checkout", "-q", "-b", "feat")
    r.base = r.git("rev-parse", "HEAD")
    return r


def head_script(r, stage="design", env=None):
    args = [sys.executable, str(r.p / "scripts" / "security_gate.py"), "check", "--feature", FEAT, "--stage", stage, "--epic", EPIC, "--repo", str(r.p), "--bd-json", str(r.epic(r.base))]
    p = subprocess.run(args, capture_output=True, text=True, env={**os.environ, **(env or {})}, cwd=r.p)
    assert len(r.git("worktree", "list").splitlines()) == 1
    return p.returncode, p.stdout, p.stderr


def test_worker_moves_base_forward_in_working_tree_and_label(tmp_path):
    r = add_design(design_repo(tmp_path))
    fwd = r.git("rev-parse", "HEAD")
    text = (r.p / REV).read_text().replace(r.base, fwd)
    r.w(REV, text)
    fails(chk(r, "design", fwd), "differs from recorded base")


def test_worker_commits_forged_base_in_reviews_rst_and_label(tmp_path):
    r = add_design(design_repo(tmp_path))
    fwd = r.git("rev-parse", "HEAD")
    text = (r.p / REV).read_text().replace(r.base, fwd)
    r.w(REV, text)
    r.commit("move base forward")
    fails(chk(r, "design", fwd), "differs from recorded base")
    fails(chk(r, "design", r.base), "differs from the run's first recorded base")


def test_forged_second_record_cannot_move_base(tmp_path):
    r = design_repo(tmp_path)
    r.w(REV, table([row("design", r.base, r.base, r.tree())]))
    r.commit("honest first record")
    fwd = r.git("rev-parse", "HEAD")
    r.w(REV, table([row("design", fwd, fwd, r.tree())]))
    r.commit("forged second")
    fails(chk(r, "design", fwd), "differs from recorded base")


def test_two_different_base_labels(tmp_path):
    r = add_design(design_repo(tmp_path))
    other = r.git("rev-parse", "main")
    fails(chk(r, "design", r.base, labels=[f"base={r.base}", f"base={other}", f"run={RUN}"]), "exactly one base= label (found 2)")


def test_base_label_is_not_a_commit(tmp_path):
    r = add_design(design_repo(tmp_path))
    fails(chk(r, "design", "zzzzzzz"), "differs from recorded base")


def test_record_base_field_not_ancestor_of_head(tmp_path):
    r = design_repo(tmp_path)
    r.git("checkout", "-q", "-b", "side", "main")
    r.w("s.txt", "s\n")
    side = r.commit("side")
    r.git("checkout", "-q", "feat-b")
    r.base = side
    add_design(r)
    fails(chk(r, "design", side), "is not an ancestor of HEAD")


def test_stacked_branch_main_fast_forwards_past_base(tmp_path):
    r = Repo(tmp_path / "st")
    r.w("docs/source/specs/features/f.rst", SPEC)
    r.w(TM, threat())
    r.w(REV, table([]))
    c0 = r.commit("c0")
    r.git("checkout", "-q", "-b", "feat-a")
    r.w("a.txt", "a\n")
    a1 = r.commit("a1")
    r.git("checkout", "-q", "-b", "feat-b")
    r.base = c0
    add_design(r)
    ok(chk(r, "design", c0))
    r.git("branch", "-f", "main", a1)
    fails(chk(r, "design", c0), "is not an ancestor of base")


def test_stacked_base_on_top_of_merge_base_passes_after_main_moves(tmp_path):
    r = add_design(design_repo(tmp_path))
    ok(chk(r, "design", r.base))
    r.git("checkout", "-q", "main")
    r.w("more.txt", "more\n")
    r.commit("main moves again")
    r.git("checkout", "-q", "feat-b")
    ok(chk(r, "design", r.base))


def test_forged_post_record_in_commit_not_latest_touching_reviews(tmp_path):
    r = post_with(tmp_path, "fp", "tests/conftest.py", "-")
    fails(chk(r, "post", r.base), "protected path tests/conftest.py changed")
    rows = [row("design", r.base, r.base, r.tree()), row("post", r.base, r.i1, r.tree(), "tests/conftest.py=accepted " + SEC, "3")]
    r.w(REV, table(rows))
    r.commit("worker forges the listing")
    ok(chk(r, "post", r.base))
    r.w(REV, table(rows) + "\n.. note:: later edit\n")
    r.commit("another reviews.rst commit buries the forged one")
    fails(chk(r, "post", r.base), "was not added by the latest commit touching reviews.rst")


@pytest.mark.parametrize("path", ["tests/conftest.py", "hooks/x.sh", ".claude-plugin/plugin.json", "docs/source/conf.py", "agents/a.md", "pyproject.toml", ".claude/settings.json", "mcp-servers.json", "skills/new/SKILL.md"])
def test_protected_path_changed_without_decision_fails_and_with_passes(tmp_path, path):
    r = post_with(tmp_path, "pp", path, "-")
    fails(chk(r, "post", r.base), f"protected path {path} changed")


@pytest.mark.parametrize("path", ["tests/conftest.py", "hooks/x.sh", ".claude-plugin/plugin.json", "docs/source/conf.py", "agents/a.md", "pyproject.toml", "mcp-servers.json"])
def test_protected_path_with_operator_decision_passes(tmp_path, path):
    r = post_with(tmp_path, "pq", path, f"{path}=accepted")
    ok(chk(r, "post", r.base))


def test_protected_decision_for_other_path_does_not_cover(tmp_path):
    r = post_with(tmp_path, "pr", "hooks/x.sh", "hooks/y.sh=accepted tests/**=accepted")
    fails(chk(r, "post", r.base), "protected path hooks/x.sh changed")


def test_unprotected_change_needs_no_decision(tmp_path):
    r = post_with(tmp_path, "pu", "src/app.py", "-")
    ok(chk(r, "post", r.base))


def test_protected_change_before_design_head_is_not_counted(tmp_path):
    r = script_repo(tmp_path, "pd")
    r.w("hooks/early.sh", "x\n")
    r.base = r.commit("early protected change")
    add_design(r)
    r.w("src/z.py", "z\n")
    i1 = r.commit("impl")
    r.w(TM, threat("mitigated", decided=True))
    r.w(REV, table([row("design", r.base, r.base, r.tree()), row("post", r.base, i1, r.tree(), SEC, "2")]))
    r.commit("post")
    ok(chk(r, "post", r.base))
    r.w("hooks/late.sh", "x\n")
    r.commit("late")
    fails(chk(r, "post", r.base), "hooks/late.sh changed after post record head")


def test_post_code_commit_after_record_head_fails(tmp_path):
    r = post_repo(tmp_path)
    r.w("src/evil.py", "x\n")
    r.commit("code after record")
    fails(chk(r, "post", r.base), "src/evil.py changed after post record head")


def test_post_only_allowed_paths_after_record_head_passes(tmp_path):
    r = post_repo(tmp_path)
    r.w(".beads/issues.jsonl", "{}\n")
    r.commit("bd")
    r.w(f"docs/source/design_log/{FEAT}-{RUN}.rst", "log\n")
    r.commit("log")
    r.w("docs/source/security/accepted-risks.rst", "r\n")
    r.w("docs/source/security/threat-model/other.rst", "t\n")
    r.commit("security docs")
    ok(chk(r, "post", r.base))


@pytest.mark.parametrize("path", [".beadsx/a", "docs/source/security_extra/x.rst", "docs/source/design_log/other.rst", f"docs/source/design_log/{FEAT}-{RUN}.txt", f"docs/source/design_log/sub/{FEAT}-{RUN}.rst", "docs/source/securityx.rst"])
def test_post_lookalike_paths_after_head_fail(tmp_path, path):
    r = post_repo(tmp_path)
    r.w(path, "x\n")
    r.commit("lookalike")
    fails(chk(r, "post", r.base), f"{path} changed after post record head")


def test_post_mixed_commit_names_only_the_bad_path(tmp_path):
    r = post_repo(tmp_path)
    r.w(".beads/x", "x\n")
    r.w("src/bad.py", "x\n")
    r.commit("mixed")
    rc, out, err = chk(r, "post", r.base)
    assert rc == 1 and "src/bad.py changed after post record head" in err and ".beads/x changed" not in err


def test_post_code_change_then_reverted_passes_diff_rule(tmp_path):
    r = post_repo(tmp_path)
    r.w("src/tmp.py", "x\n")
    r.commit("add")
    (r.p / "src/tmp.py").unlink()
    r.commit("remove")
    ok(chk(r, "post", r.base))


def test_post_code_deleted_after_record_fails(tmp_path):
    r = post_with(tmp_path, "pdel", "src/app.py", "-")
    (r.p / "src/app.py").unlink()
    r.commit("delete code after record")
    fails(chk(r, "post", r.base), "src/app.py changed after post record head")


@pytest.mark.parametrize("op", ["modify", "add", "delete", "rename", "nested_add"])
def test_tree_hash_changes_under_skills_fail(tmp_path, op):
    r = add_design(design_repo(tmp_path))
    ok(chk(r, "design", r.base))
    s = r.p / "skills"
    if op == "modify":
        r.w("skills/s.md", "skill v1 edited\n")
    elif op == "add":
        r.w("skills/new.md", "n\n")
    elif op == "delete":
        (s / "s.md").unlink()
    elif op == "rename":
        (s / "s.md").rename(s / "t.md")
    else:
        r.w("skills/a/b/c.md", "n\n")
    fails(chk(r, "design", r.base), "tree sha256 differs")


@pytest.mark.parametrize("path", ["docs/source/a.rst", "docs/source/new/dir/n.rst", "docs/source/conf.py"])
def test_tree_hash_changes_under_docs_source_fail(tmp_path, path):
    r = add_design(design_repo(tmp_path))
    r.w(path, "changed\n")
    fails(chk(r, "design", r.base), "tree sha256 differs")


def test_tree_hash_uncommitted_disk_change_fails_and_is_reverted_ok(tmp_path):
    r = add_design(design_repo(tmp_path))
    r.w("skills/s.md", "dirty\n")
    fails(chk(r, "design", r.base), "tree sha256 differs")
    r.w("skills/s.md", "skill v1\n")
    ok(chk(r, "design", r.base))


@pytest.mark.parametrize("path", ["docs/source/security/extra.rst", "docs/source/security/threat-model/new.rst", "docs/source/security/accepted-risks.rst", f"docs/source/design_log/{FEAT}-{RUN}.rst"])
def test_tree_hash_ignores_security_docs_and_run_design_log(tmp_path, path):
    r = add_design(design_repo(tmp_path))
    r.w(path, "changed\n")
    ok(chk(r, "design", r.base))


def test_tree_hash_ignores_pycache(tmp_path):
    r = add_design(design_repo(tmp_path))
    r.w("skills/__pycache__/x.cpython-313.pyc", "bin\n")
    r.w("skills/y.pyc", "bin\n")
    ok(chk(r, "design", r.base))


def test_tree_hash_other_feature_or_run_design_log_counts(tmp_path):
    r = add_design(design_repo(tmp_path))
    r.w("docs/source/design_log/FEAT-X-bbbbbbbb.rst", "x\n")
    fails(chk(r, "design", r.base), "tree sha256 differs")


def test_threat_decided_by_operator_but_other_run_is_undecided(tmp_path):
    r = design_repo(tmp_path)
    r.w(TM, threat(decided=True).replace(f":run: {RUN}", ":run: bbbbbbbb"))
    r.w(REV, table([row("design", r.base, r.base, r.tree())]))
    r.commit("rec")
    fails(chk(r, "design", r.base), f"is open without a decision for run {RUN}")


@pytest.mark.parametrize("who", ["agent", "not-operator", "", "worker"])
def test_threat_right_run_but_not_decided_by_operator_is_undecided(tmp_path, who):
    r = design_repo(tmp_path)
    r.w(TM, threat(decided=True).replace(":decided_by: operator", f":decided_by: {who}"))
    r.w(REV, table([row("design", r.base, r.base, r.tree())]))
    r.commit("rec")
    fails(chk(r, "design", r.base), "is open without a decision")


def test_threat_decision_with_run_list_counts(tmp_path):
    r = design_repo(tmp_path)
    r.w(TM, threat(decided=True).replace(f":run: {RUN}", f":run: bbbbbbbb, {RUN}"))
    r.w(REV, table([row("design", r.base, r.base, r.tree())]))
    r.commit("rec")
    ok(chk(r, "design", r.base))


def test_threat_linked_only_to_other_feature_is_ignored(tmp_path):
    r = design_repo(tmp_path)
    r.w("docs/source/specs/features/g.rst", ".. feat:: Y\n   :id: FEAT-Y\n\n.. req:: R\n   :id: REQ-Y-001\n   :links: FEAT-Y\n")
    r.w("docs/source/security/threat-model/other-box.rst", ".. threat:: o\n   :id: THREAT-OTHER-BOX-001\n   :status: open\n   :links: REQ-Y-001\n")
    r.commit("other feature threat")
    r = add_design(r)
    ok(chk(r, "design", r.base))


def test_post_threat_linked_only_to_other_feature_is_ignored(tmp_path):
    r = post_repo(tmp_path)
    r.w("docs/source/specs/features/g.rst", ".. feat:: Y\n   :id: FEAT-Y\n\n.. req:: R\n   :id: REQ-Y-001\n   :links: FEAT-Y\n")
    r.w("docs/source/security/threat-model/other-box.rst", ".. threat:: o\n   :id: THREAT-OTHER-BOX-001\n   :status: open\n   :links: REQ-Y-001\n")
    r.commit("other open threat")
    rc, out, err = chk(r, "post", r.base)
    assert "THREAT-OTHER-BOX-001" not in err


def test_post_threat_linked_to_other_feature_but_also_ours_counts(tmp_path):
    r = post_repo(tmp_path)
    r.w(TM, threat("open", decided=True).replace("links: REQ-X-001", "links: REQ-X-001, REQ-Y-001"))
    r.commit("reopen")
    fails(chk(r, "post", r.base), "THREAT-MY-BOX-001 is open")


def test_design_rule_does_not_apply_decision_exemption_to_post(tmp_path):
    r = post_repo(tmp_path)
    r.w(TM, threat("open", decided=True))
    r.commit("reopen with decision")
    fails(chk(r, "post", r.base), "is open")


@pytest.mark.parametrize("status", ["OPEN", "Open", "", "opened"])
def test_threat_status_spelling_does_not_hide_open_threat(tmp_path, status):
    r = design_repo(tmp_path)
    r.w(TM, threat(status))
    r.w(REV, table([row("design", r.base, r.base, r.tree())]))
    r.commit("rec")
    rc, out, err = chk(r, "design", r.base)
    assert rc == 1, (status, err)


def test_reexec_head_lib_always_passes_but_base_version_still_fails(tmp_path):
    r = script_repo(tmp_path, "rx")
    add_design(r, tree="0" * 64)
    lp = r.p / "scripts" / "security_gate_lib.py"
    lp.write_text(lp.read_text() + "\n_orig = run_check\n\n\ndef run_check(*a):\n    e, b = _orig(*a)\n    return [], b\n")
    r.commit("head lib forced to pass")
    rc, out, err = head_script(r, env={"SDD_GATE_REEXEC": "1"})
    assert rc == 0, (out, err)
    rc, out, err = head_script(r)
    assert rc == 1 and "tree sha256 differs" in err, (out, err)


def test_reexec_when_only_lib_differs(tmp_path):
    r = script_repo(tmp_path, "rl")
    add_design(r, tree="0" * 64)
    lp = r.p / "scripts" / "security_gate_lib.py"
    lp.write_text(lp.read_text() + "\n_orig = run_check\n\n\ndef run_check(*a):\n    return [], _orig(*a)[1]\n")
    r.commit("lib only")
    fails(head_script(r), "tree sha256 differs")


def test_reexec_when_only_entry_script_differs(tmp_path):
    r = script_repo(tmp_path, "re")
    add_design(r, tree="0" * 64)
    sp = r.p / "scripts" / "security_gate.py"
    sp.write_text(sp.read_text().replace("errs, base = lib.run_check(repo, docs, a.feature, a.stage, a.epic, a.main, epic)\n", "errs, base = lib.run_check(repo, docs, a.feature, a.stage, a.epic, a.main, epic)\n    errs = []\n"))
    r.commit("entry script forced to pass")
    rc, out, err = head_script(r)
    assert rc == 1 and "tree sha256 differs" in err, (out, err)


def test_reexec_uses_isolated_interpreter(tmp_path):
    r = script_repo(tmp_path, "ri")
    add_design(r)
    lp = r.p / "scripts" / "security_gate_lib.py"
    lp.write_text(lp.read_text() + "\n")
    r.commit("lib differs")
    evil = tmp_path / "evil"
    evil.mkdir()
    marker = tmp_path / "marker"
    (evil / "sitecustomize.py").write_text(f"import os\nif os.environ.get('SDD_GATE_REEXEC'):\n    open({str(marker)!r}, 'w').write('x')\n")
    rc, out, err = head_script(r, env={"PYTHONPATH": str(evil)})
    assert rc == 0, (out, err)
    assert not marker.exists()


def test_reexec_leaves_no_worktree_on_success_or_failure(tmp_path):
    r = script_repo(tmp_path, "rw")
    add_design(r, tree="0" * 64)
    lp = r.p / "scripts" / "security_gate_lib.py"
    lp.write_text(lp.read_text() + "\n")
    r.commit("lib differs")
    before = set(Path(os.environ.get("TMPDIR", "/tmp")).glob("sdd-gate-*"))
    fails(head_script(r), "tree sha256 differs")
    assert set(Path(os.environ.get("TMPDIR", "/tmp")).glob("sdd-gate-*")) <= before
    assert r.git("worktree", "list").count("\n") == 0


def test_bootstrap_line_printed_even_when_check_fails(tmp_path):
    r = add_design(design_repo(tmp_path), tree="0" * 64)
    rc, out, err = chk(r, "design", r.base)
    assert rc == 1 and "gate script unverified (bootstrap)" in out


def test_no_bootstrap_line_when_reexec_inner_runs(tmp_path):
    r = script_repo(tmp_path, "rb")
    add_design(r)
    lp = r.p / "scripts" / "security_gate_lib.py"
    lp.write_text(lp.read_text() + "\n")
    r.commit("lib differs")
    rc, out, err = head_script(r)
    assert rc == 0 and "bootstrap" not in out, (out, err)


@pytest.mark.parametrize("stage", ["design", "post"])
def test_no_worktree_left_after_plain_checks(tmp_path, stage):
    r = post_repo(tmp_path) if stage == "post" else add_design(design_repo(tmp_path))
    chk(r, stage, r.base)
    chk(r, stage, "bogus")

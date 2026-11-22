# [origin ref=llm-dsl-2zv1.3 req=REQ-SECURITY-REVIEW-008,REQ-SECURITY-REVIEW-011 c4=sdd_skills/security_review]
#   [intent]Tests security_gate.py check against temp git repos built with real git and a fake bd epic JSON, one test per failure cause.[/intent]
# [/origin]

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
GATE = SCRIPTS / "security_gate.py"
sys.path.insert(0, str(SCRIPTS))
import security_gate_lib as lib

FEAT, RUN, EPIC = "FEAT-X", "aaaaaaaa", "ep-1"
SPEC = ".. feat:: X\n   :id: FEAT-X\n\n.. req:: R\n   :id: REQ-X-001\n   :links: FEAT-X\n"
HEAD_ROW = ("run", "stage", "review", "base", "range", "tree", "protected", "findings", "outcome")


def threat(status="open", decided=False):
    extra = f"   :run: {RUN}\n   :decided_by: operator\n" if decided else ""
    return f".. threat:: t\n   :id: THREAT-MY-BOX-001\n   :status: {status}\n{extra}   :links: REQ-X-001\n"


def table(rows):
    out = ["Reviews", "=======", "", ".. list-table::", "   :header-rows: 1", ""]
    for r in [HEAD_ROW] + rows:
        vals = [c if i == 0 and r is HEAD_ROW else (c or "-") for i, c in enumerate(r)] if r is not HEAD_ROW else [c.capitalize() for c in r]
        out += [f"   * - {vals[0]}"] + [f"     - {v}" for v in vals[1:]]
    return "\n".join(out) + "\n"


def row(stage, base, head, tree="", prot="", review="1", run=RUN, outcome="ok"):
    return (run, stage, review, base, f"{base}..{head}", tree, prot, "0", outcome)


class Repo:
    def __init__(self, path: Path):
        self.p = path
        path.mkdir(parents=True, exist_ok=True)
        self.env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
        self.git("init", "-q", "-b", "main")

    def git(self, *a):
        r = subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(self.p), *a], capture_output=True, text=True, env=self.env)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def w(self, rel, text):
        f = self.p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")

    def commit(self, msg="c"):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def tree(self):
        return lib.tree_hash(self.p, FEAT, RUN)

    def epic(self, base, extra=None, labels=None):
        labels = labels if labels is not None else [f"base={base}", f"feat={FEAT}", f"run={RUN}"]
        f = self.p.parent / f"{self.p.name}-epic.json"
        f.write_text(json.dumps([{"id": EPIC, "labels": labels + (extra or [])}]))
        return f

    def check(self, stage, base, main="main", labels=None, extra_args=()):
        ef = self.epic(base, labels=labels)
        r = subprocess.run([sys.executable, str(GATE), "check", "--feature", FEAT, "--stage", stage, "--epic", EPIC, "--repo", str(self.p), "--main", main, "--bd-json", str(ef), *extra_args], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr


def design_repo(tmp_path, name="r"):
    r = Repo(tmp_path / name)
    r.w("docs/source/specs/features/f.rst", SPEC)
    r.w("docs/source/security/threat-model/my-box.rst", threat())
    r.w("docs/source/security/reviews.rst", table([]))
    r.w("skills/s.md", "skill v1\n")
    r.commit("c0 main")
    r.git("checkout", "-q", "-b", "feat-a")
    r.w("docs/source/a.rst", "A\n")
    a1 = r.commit("A1")
    r.git("checkout", "-q", "-b", "feat-b")
    r.w("docs/source/b.rst", "B\n")
    b1 = r.commit("B1 stacked")
    r.git("checkout", "-q", "main")
    r.w("other.txt", "main moved\n")
    r.commit("main moved")
    r.git("checkout", "-q", "feat-b")
    r.base = b1
    return r


def add_design(r, tree=None, outcome="ok"):
    r.w("docs/source/security/threat-model/my-box.rst", threat(decided=True))
    r.w("docs/source/security/reviews.rst", table([row("design", r.base, r.base, r.tree() if tree is None else tree, outcome=outcome)]))
    r.dsha = r.commit("design gate")
    return r


def post_repo(tmp_path, name="p"):
    r = add_design(design_repo(tmp_path, name))
    r.dtree = r.tree()
    r.w("skills/s.md", "skill v2\n")
    r.w("docs/source/c.rst", "C\n")
    i1 = r.commit("implement")
    r.w("docs/source/security/threat-model/my-box.rst", threat("mitigated", decided=True))
    rows = [row("design", r.base, r.base, r.dtree), row("post", r.base, i1, r.tree(), "skills/**=accepted docs/source/security/**=accepted", "2")]
    r.w("docs/source/security/reviews.rst", table(rows))
    r.i1 = i1
    r.psha = r.commit("post gate")
    return r


def fails(res, text):
    rc, out, err = res
    assert rc == 1 and text in err, (rc, out, err)


def test_threat_container_exact(tmp_path):
    d = tmp_path / "docs"
    (d / "security" / "threat-model").mkdir(parents=True)
    (d / "security" / "threat-model" / "my.rst").write_text(threat().replace("MY-BOX", "MY-BOX"))
    assert lib.check_records(lib.load(d)) != []
    (d / "security" / "threat-model" / "my.rst").write_text(threat().replace("THREAT-MY-BOX-001", "THREAT-MY-001"))
    assert lib.check_records(lib.load(d)) == []
    (d / "security" / "threat-model" / "my.rst").write_text(threat().replace("THREAT-MY-BOX-001", "THREAT-MY-X-1-001"))
    assert lib.check_records(lib.load(d)) != []


def test_design_pass_end_to_end(tmp_path):
    r = add_design(design_repo(tmp_path))
    rc, out, err = r.check("design", r.base)
    assert rc == 0, err
    assert "gate script unverified (bootstrap)" in out


def test_post_pass_end_to_end_with_later_bd_and_log_commits(tmp_path):
    r = post_repo(tmp_path)
    assert r.check("post", r.base)[0] == 0
    r.w(".beads/issues.jsonl", "{}\n")
    r.w(f"docs/source/design_log/{FEAT}-{RUN}.rst", "log\n")
    r.w("docs/source/security/accepted-risks.rst", "more\n")
    r.commit("bd + log")
    rc, out, err = r.check("post", r.base)
    assert rc == 0, err


def test_no_record_for_stage(tmp_path):
    r = add_design(design_repo(tmp_path))
    fails(r.check("post", r.base), f"no review record for run {RUN} stage post")


def test_tree_hash_mismatch(tmp_path):
    r = add_design(design_repo(tmp_path))
    r.w("skills/s.md", "tampered\n")
    fails(r.check("design", r.base), "tree sha256 differs")


def test_tree_hash_missing(tmp_path):
    r = add_design(design_repo(tmp_path), tree="-")
    fails(r.check("design", r.base), "has no tree hash")


def test_tree_hash_ignores_security_docs_and_design_log(tmp_path):
    r = add_design(design_repo(tmp_path))
    r.w("docs/source/security/extra.rst", "x\n")
    r.w(f"docs/source/design_log/{FEAT}-{RUN}-more.rst", "x\n")
    assert r.check("design", r.base)[0] == 0
    r.w("docs/source/design_log/other.rst", "x\n")
    fails(r.check("design", r.base), "tree sha256 differs")


def test_design_open_threat_without_decision(tmp_path):
    r = design_repo(tmp_path)
    r.w("docs/source/security/reviews.rst", table([row("design", r.base, r.base, r.tree())]))
    r.commit("record only")
    fails(r.check("design", r.base), f"THREAT-MY-BOX-001 is open without a decision for run {RUN}")


def test_design_decision_for_other_run_does_not_count(tmp_path):
    r = design_repo(tmp_path)
    r.w("docs/source/security/threat-model/my-box.rst", threat(decided=True).replace(f":run: {RUN}", ":run: bbbbbbbb"))
    r.w("docs/source/security/reviews.rst", table([row("design", r.base, r.base, r.tree())]))
    r.commit("record")
    fails(r.check("design", r.base), "open without a decision")


def test_post_open_threat_even_with_decision(tmp_path):
    r = post_repo(tmp_path)
    r.w("docs/source/security/threat-model/my-box.rst", threat("open", decided=True))
    r.commit("reopen")
    fails(r.check("post", r.base), "THREAT-MY-BOX-001 is open")


def test_post_head_differs_with_outside_change(tmp_path):
    r = post_repo(tmp_path)
    r.w("docs/source/sneaky.rst", "x\n")
    r.commit("sneak")
    rc, out, err = r.check("post", r.base)
    assert rc == 1 and "docs/source/sneaky.rst changed after post record head" in err
    assert "tree sha256 differs" in err


def test_post_head_not_ancestor(tmp_path):
    r = post_repo(tmp_path)
    r.git("checkout", "-q", "-b", "side", r.base)
    r.w("z.txt", "z\n")
    z = r.commit("side")
    r.git("checkout", "-q", "feat-b")
    text = (r.p / "docs/source/security/reviews.rst").read_text().replace(r.i1, z)
    r.w("docs/source/security/reviews.rst", text)
    r.commit("rewrite head")
    fails(r.check("post", r.base), "is not an ancestor of HEAD")


def test_protected_change_not_listed(tmp_path):
    r = post_repo(tmp_path)
    text = (r.p / "docs/source/security/reviews.rst").read_text().replace("skills/**=accepted", "-")
    r.w("docs/source/security/reviews.rst", text)
    r.commit("drop listing")
    fails(r.check("post", r.base), "protected path skills/s.md changed since design head")


def test_protected_listed_but_not_rejected_marker(tmp_path):
    r = post_repo(tmp_path)
    text = (r.p / "docs/source/security/reviews.rst").read_text().replace("skills/**=accepted", "skills/**=rejected")
    r.w("docs/source/security/reviews.rst", text)
    r.commit("rejected")
    fails(r.check("post", r.base), "protected path skills/s.md changed")


def test_protected_post_record_not_in_latest_reviews_commit(tmp_path):
    r = post_repo(tmp_path)
    text = (r.p / "docs/source/security/reviews.rst").read_text()
    r.w("docs/source/security/reviews.rst", text + "\n.. note: x\n")
    r.commit("touch reviews again without adding a record")
    fails(r.check("post", r.base), "was not added by the latest commit touching reviews.rst")


def test_protected_set_read_from_rules_section(tmp_path):
    r = design_repo(tmp_path)
    r.w("skills/rules/RULES.md", "# R\n\n## Protected set\n\n- `custom/**`\n\n## Next\n\n- `skills/**`\n")
    r.commit("rules")
    add_design(r)
    r.w("custom/x.txt", "x\n")
    i1 = r.commit("impl")
    r.w("docs/source/security/threat-model/my-box.rst", threat("mitigated", decided=True))
    r.w("docs/source/security/reviews.rst", table([row("design", r.base, r.base, r.tree()), row("post", r.base, i1, r.tree(), "-", "2")]))
    r.commit("post")
    fails(r.check("post", r.base), "protected path custom/x.txt changed")
    r.w("docs/source/security/reviews.rst", table([row("design", r.base, r.base, r.tree()), row("post", r.base, i1, r.tree(), "-", "2"), row("post", r.base, i1, r.tree(), "custom/x.txt=accepted", "3")]))
    r.commit("list it")
    rc, out, err = r.check("post", r.base)
    assert "protected path custom/x.txt" not in err, err


def test_epic_base_label_missing_and_duplicate(tmp_path):
    r = add_design(design_repo(tmp_path))
    fails(r.check("design", r.base, labels=[f"run={RUN}", f"feat={FEAT}"]), "exactly one base= label (found 0)")
    fails(r.check("design", r.base, labels=[f"base={r.base}", f"base={r.base}", f"run={RUN}"]), "exactly one base= label (found 2)")


def test_epic_base_label_differs(tmp_path):
    r = add_design(design_repo(tmp_path))
    other = r.git("rev-parse", "main")
    fails(r.check("design", other), "differs from recorded base")


def test_epic_base_label_short_sha_accepted(tmp_path):
    r = add_design(design_repo(tmp_path))
    assert r.check("design", r.base[:8])[0] == 0


def test_base_read_from_git_not_working_tree(tmp_path):
    r = add_design(design_repo(tmp_path))
    forged = r.git("rev-parse", "main")
    text = (r.p / "docs/source/security/reviews.rst").read_text().replace(r.base, forged)
    r.w("docs/source/security/reviews.rst", text)
    fails(r.check("design", forged), "differs from recorded base")


def test_first_record_not_committed(tmp_path):
    r = design_repo(tmp_path)
    r.w("docs/source/security/reviews.rst", table([row("design", r.base, r.base, r.tree())]))
    fails(r.check("design", r.base), "first review record is not committed")


def test_first_record_without_base(tmp_path):
    r = design_repo(tmp_path)
    r.w("docs/source/security/reviews.rst", table([row("design", "", r.base, r.tree())]))
    r.commit("no base")
    fails(r.check("design", r.base), "has no base")


def test_base_not_ancestor_of_head(tmp_path):
    r = design_repo(tmp_path)
    r.git("checkout", "-q", "-b", "side", "main")
    r.w("s.txt", "s\n")
    side = r.commit("side")
    r.git("checkout", "-q", "feat-b")
    r.base = side
    add_design(r)
    fails(r.check("design", side), f"base {side[:8]} is not an ancestor of HEAD")


def test_merge_base_not_ancestor_of_base(tmp_path):
    r = Repo(tmp_path / "m")
    r.w("docs/source/specs/features/f.rst", SPEC)
    r.w("docs/source/security/threat-model/my-box.rst", threat())
    r.w("docs/source/security/reviews.rst", table([]))
    old = r.commit("old")
    r.w("m.txt", "m\n")
    r.commit("m1")
    r.git("checkout", "-q", "-b", "feat")
    r.base = old
    add_design(r)
    fails(r.check("design", old), "is not an ancestor of base")


def test_merge_base_equal_to_base_ok(tmp_path):
    r = Repo(tmp_path / "e")
    r.w("docs/source/specs/features/f.rst", SPEC)
    r.w("docs/source/security/threat-model/my-box.rst", threat())
    r.w("docs/source/security/reviews.rst", table([]))
    c0 = r.commit("c0")
    r.git("checkout", "-q", "-b", "feat")
    r.base = c0
    add_design(r)
    assert r.check("design", c0)[0] == 0


def test_main_branch_missing_and_configurable(tmp_path):
    r = add_design(design_repo(tmp_path))
    fails(r.check("design", r.base, main="nomain"), "main branch nomain not found")
    r.git("branch", "trunk", "main")
    assert r.check("design", r.base, main="trunk")[0] == 0


def test_rebase_record_requires_operator_decision(tmp_path):
    r = add_design(design_repo(tmp_path))
    new = r.git("rev-parse", "HEAD")
    rows = [row("design", r.base, r.base, r.tree()), row("rebase", new, new, "", "", "2", outcome="agent proposal")]
    r.w("docs/source/security/reviews.rst", table(rows))
    r.commit("rebase unconfirmed")
    fails(r.check("design", new), "differs from recorded base")
    rows.append(row("rebase", new, new, "", "", "3", outcome="decided_by=operator 2026-11-22"))
    r.w("docs/source/security/reviews.rst", table(rows))
    r.commit("rebase confirmed")
    rc, out, err = r.check("design", new)
    assert rc == 0, err
    fails(r.check("design", r.base), "differs from recorded base")


def test_epic_without_run_label(tmp_path):
    r = add_design(design_repo(tmp_path))
    fails(r.check("design", r.base, labels=[f"base={r.base}"]), "exactly one run= label")


def test_epic_json_from_env_command(tmp_path):
    r = add_design(design_repo(tmp_path))
    ef = r.epic(r.base)
    fake = tmp_path / "fakebd.sh"
    fake.write_text(f"#!/bin/sh\ncat {ef}\n")
    fake.chmod(0o755)
    env = {**os.environ, "SDD_BD_SHOW_CMD": str(fake)}
    res = subprocess.run([sys.executable, str(GATE), "check", "--feature", FEAT, "--stage", "design", "--epic", EPIC, "--repo", str(r.p)], capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr


def test_bootstrap_line_absent_script_and_silent_when_same(tmp_path):
    r = Repo(tmp_path / "b")
    r.w("docs/source/specs/features/f.rst", SPEC)
    r.w("docs/source/security/threat-model/my-box.rst", threat())
    r.w("docs/source/security/reviews.rst", table([]))
    r.w("scripts/security_gate.py", GATE.read_text())
    shutil.copy(SCRIPTS / "security_gate_lib.py", r.p / "scripts")
    r.commit("c0 with script")
    r.git("checkout", "-q", "-b", "feat")
    r.base = r.git("rev-parse", "HEAD")
    add_design(r)
    rc, out, err = r.check("design", r.base)
    assert rc == 0 and "bootstrap" not in out, (out, err)


def test_base_version_reexecuted_when_script_differs(tmp_path):
    r = Repo(tmp_path / "x")
    r.w("docs/source/specs/features/f.rst", SPEC)
    r.w("docs/source/security/threat-model/my-box.rst", threat())
    r.w("docs/source/security/reviews.rst", table([]))
    r.w("scripts/security_gate.py", GATE.read_text())
    shutil.copy(SCRIPTS / "security_gate_lib.py", r.p / "scripts")
    r.commit("c0 with script")
    r.git("checkout", "-q", "-b", "feat")
    r.base = r.git("rev-parse", "HEAD")
    add_design(r)
    lib_p = r.p / "scripts" / "security_gate_lib.py"
    lib_p.write_text(lib_p.read_text() + "\nraise SystemExit(99)\n")
    r.commit("head script is broken")
    res = r.check("design", r.base)
    assert res[0] == 0, res
    out = subprocess.run([sys.executable, str(r.p / "scripts" / "security_gate.py"), "check", "--feature", FEAT, "--stage", "design", "--epic", EPIC, "--repo", str(r.p), "--bd-json", str(r.epic(r.base))], capture_output=True, text=True)
    assert out.returncode == 99
    assert r.git("worktree", "list").count("\n") == 0


def test_base_version_failure_propagates(tmp_path):
    r = Repo(tmp_path / "y")
    r.w("docs/source/specs/features/f.rst", SPEC)
    r.w("docs/source/security/threat-model/my-box.rst", threat())
    r.w("docs/source/security/reviews.rst", table([]))
    r.w("scripts/security_gate.py", GATE.read_text())
    shutil.copy(SCRIPTS / "security_gate_lib.py", r.p / "scripts")
    r.commit("c0")
    r.git("checkout", "-q", "-b", "feat")
    r.base = r.git("rev-parse", "HEAD")
    add_design(r, tree="-")
    (r.p / "scripts" / "security_gate.py").write_text(GATE.read_text() + "\n")
    r.commit("script changed")
    fails(r.check("design", r.base), "has no tree hash")


def test_tree_hash_command_matches_lib(tmp_path):
    r = add_design(design_repo(tmp_path))
    out = subprocess.run([sys.executable, str(GATE), "tree-hash", "--feature", FEAT, "--run", RUN, "--repo", str(r.p)], capture_output=True, text=True)
    assert out.stdout.strip() == r.tree()


def test_real_repo_fails_with_bootstrap_state():
    if shutil.which("bd") is None or subprocess.run(["bd", "show", "llm-dsl-2zv1", "--json"], capture_output=True, text=True).returncode != 0:
        pytest.skip("bd epic llm-dsl-2zv1 not available")
    res = subprocess.run([sys.executable, str(GATE), "check", "--stage", "design", "--feature", "FEAT-SECURITY-REVIEW", "--epic", "llm-dsl-2zv1"], capture_output=True, text=True, cwd=ROOT)
    assert res.returncode == 1
    assert "no tree hash" in res.stderr or "has no base" in res.stderr or "no review record" in res.stderr


def test_validate_rejects_unknown_threat_status(tmp_path):
    d = tmp_path / "docs"
    (d / "security" / "threat-model").mkdir(parents=True)
    f = d / "security" / "threat-model" / "my-box.rst"
    for st, n in (("OPEN", 1), ("closed", 1), ("open", 0), ("mitigated", 0)):
        f.write_text(threat(st))
        errs = [e for e in lib.check_records(lib.load(d)) if "status" in e]
        assert len(errs) == n, (st, errs)


def test_rebase_row_only_from_committed_history(tmp_path):
    r = add_design(design_repo(tmp_path))
    new = r.git("rev-parse", "HEAD")
    rows = [row("design", r.base, r.base, r.tree()), row("rebase", new, new, "", "", "2", outcome="decided_by=operator")]
    r.w("docs/source/security/reviews.rst", table(rows))
    fails(r.check("design", new), "differs from recorded base")
    r.commit("rebase committed")
    assert r.check("design", new)[0] == 0


def test_rebase_row_needs_structured_marker(tmp_path):
    r = add_design(design_repo(tmp_path))
    new = r.git("rev-parse", "HEAD")
    rows = [row("design", r.base, r.base, r.tree()), row("rebase", new, new, "", "", "2", outcome="not decided_by=operator really")]
    r.w("docs/source/security/reviews.rst", table(rows))
    r.commit("substring")
    fails(r.check("design", new), "differs from recorded base")


def test_edited_post_row_is_not_added(tmp_path):
    r = post_repo(tmp_path)
    text = (r.p / "docs/source/security/reviews.rst").read_text()
    r.w("docs/source/security/reviews.rst", text.replace("     - ok\n", "     - edited\n"))
    r.commit("edit existing rows")
    fails(r.check("post", r.base), "was not added by the latest commit touching reviews.rst")


def append_only(r, *args):
    p = subprocess.run([sys.executable, str(GATE), "append-only", "--run", RUN, "--repo", str(r.p), *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def test_check_runs_append_only_altered_row_between_gates(tmp_path):
    r = post_repo(tmp_path)
    assert r.check("post", r.base)[0] == 0
    text = (r.p / "docs/source/security/reviews.rst").read_text()
    r.w("docs/source/security/reviews.rst", text.replace("     - ok\n", "     - rewritten\n", 1))
    r.commit("alter design row")
    fails(r.check("post", r.base), "altered")


def test_check_runs_append_only_removed_threat_design(tmp_path):
    r = add_design(design_repo(tmp_path))
    assert r.check("design", r.base)[0] == 0
    r.w("docs/source/security/threat-model/my-box.rst", "")
    r.commit("drop threats")
    rc, out, err = r.check("design", r.base)
    assert rc == 1 and "disappeared" in err


def test_append_only_working_tree_sees_uncommitted_edit(tmp_path):
    r = add_design(design_repo(tmp_path))
    assert append_only(r, "--since", r.base)[0] == 0
    f = r.p / "docs/source/security/reviews.rst"
    f.write_text(f.read_text().replace("     - ok\n", "     - rewritten\n", 1))
    assert append_only(r, "--since", r.dsha)[0] == 0
    rc, out, err = append_only(r, "--since", r.dsha, "--working-tree")
    assert rc == 1 and "altered" in err
    r.commit("commit the edit")
    assert append_only(r, "--since", r.dsha)[0] == 1


def test_threat_without_req_link_counts_for_feature_and_is_reported(tmp_path):
    r = design_repo(tmp_path)
    r.w("docs/source/security/threat-model/my-box.rst", threat(decided=True) + "\n.. threat:: n\n   :id: THREAT-MY-BOX-002\n   :status: mitigated\n   :links: THREAT-MY-BOX-001\n")
    r.w("docs/source/security/reviews.rst", table([row("design", r.base, r.base, r.tree())]))
    r.commit("rec")
    fails(r.check("design", r.base), "THREAT-MY-BOX-002 has no REQ link")


def test_unlinked_open_threat_fails_post(tmp_path):
    r = post_repo(tmp_path)
    f = r.p / "docs/source/security/threat-model/my-box.rst"
    f.write_text(f.read_text() + "\n.. threat:: n\n   :id: THREAT-MY-BOX-002\n   :status: open\n   :links:\n")
    r.commit("unlinked open threat")
    rc, out, err = r.check("post", r.base)
    assert rc == 1 and "THREAT-MY-BOX-002 is open" in err


def test_validate_finding_needs_feature_req_link(tmp_path):
    d = tmp_path / "docs"
    (d / "specs").mkdir(parents=True)
    (d / "specs" / "f.rst").write_text(SPEC)
    (d / "security" / "threat-model").mkdir(parents=True)
    (d / "security" / "threat-model" / "my-box.rst").write_text(threat())
    data = lib.load(d)
    base = {"id": "F1", "severity": "high", "stride": "T", "element": "x", "anchor": "a", "threat": "t", "mitigation": "m"}
    data["c4"] = {"x"}
    for links, bad in (([], True), (["THREAT-MY-BOX-001"], True), (["REQ-X-001"], False), (["THREAT-MY-BOX-001", "REQ-X-001"], False)):
        errs = lib.validate_findings([{**base, "links": links}], data, FEAT)
        assert bool([e for e in errs if "REQ id" in e]) == bad, (links, errs)

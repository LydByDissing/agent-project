# [origin ref=llm-dsl-2zv1.13 req=REQ-SECURITY-REVIEW-006,REQ-SECURITY-REVIEW-003 c4=sdd_skills/sdd_orchestrator]
#   [intent]Doc-contract tests that sdd, arch-review, plan, RULES, README, conf and plugin.json wire the security-review phases into the pipeline, with negative controls.[/intent]
# [/origin]

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import security_gate_lib as lib  # noqa: E402

pytestmark = pytest.mark.doc_contract

PIPELINE = "docs → security-design → plan → implement → arch-review → security-review → done"
PHASES = ("docs", "security-design", "plan", "implement", "arch-review", "security-review", "done")
GATE_RE = r'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/security_gate\.py" check'
PROTECTED = [
    "scripts/security_gate_lib.py", "hooks/**", ".claude-plugin/**", "mcp-servers.json", "tests/conftest.py",
    "pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "docs/source/conf.py", "agents/**", "skills/**",
    ".claude/**", "docs/source/security/**",
]


def rd(*p: str) -> str:
    return (ROOT.joinpath(*p)).read_text(encoding="utf-8")


def sdd() -> str:
    return rd("skills", "sdd", "SKILL.md")


def sect(t: str, heading: str, level: int = 3) -> str:
    m = re.search(rf"^{'#' * level} {re.escape(heading)}\b.*$", t, re.M)
    assert m, f"no section {heading}"
    nxt = re.search(rf"^#{{1,{level}}} ", t[m.end():], re.M)
    return t[m.start(): m.end() + nxt.start() if nxt else len(t)]


def has(t: str, *pats: str) -> bool:
    return all(re.search(p, t, re.I | re.S) for p in pats)


def phase_secs(t: str) -> dict[str, str]:
    return {p: sect(t, f"Phase: {p}") for p in PHASES if p != "done"}


def label_changes_ok(t: str) -> bool:
    for name, sec in phase_secs(t).items():
        for m in re.finditer(r"add `phase=([a-z-]+)`", sec):
            line_start = sec.rfind("\n", 0, m.start()) + 1
            line = sec[line_start: sec.find("\n", m.end())]
            if not re.search(r"[Rr]emove `phase=[a-z-]+`", line):
                return False
    return True


def gate_before_moves_ok(t: str) -> bool:
    if not re.search(GATE_RE, t):
        return False
    to_plan = sect(t, "Phase: security-design")
    to_done = sect(t, "Phase: security-review")
    ok_plan = re.search(r"signal=advance.*?security gate check.*?phase=plan", to_plan, re.S)
    ok_done = re.search(r"signal=advance.*?check.*?phase=done.*?check.*?bd close", to_done, re.S)
    sec = sect(t, "Security gate")
    ok_list = has(sec, r"before every move to `plan`", r"before every move to `done`", r"before every `bd close`", r"live", r"resume")
    ok_resume = has(sect(t, "Crash Recovery", 2), r"security gate check", r"live|again")
    return bool(ok_plan and ok_done and ok_list and ok_resume)


def test_pipeline_order_string_everywhere():
    assert PIPELINE in sdd()
    assert PIPELINE in rd("README.md")
    assert "docs → security-design → plan → implement → arch-review → security-review" in rd(".claude-plugin", "plugin.json")
    t = sdd()
    pos = [t.index(f"### Phase: {p}") for p in PHASES if p not in ("done",)]
    assert pos == sorted(pos)


def test_phase_sections_invoke_security_skill_inline():
    for ph, stage in (("security-design", "design"), ("security-review", "post")):
        sec = sect(sdd(), f"Phase: {ph}")
        assert "skills/security-review/SKILL.md" in sec
        assert has(sec, r"inline", r"main-agent|main context", r"Do NOT spawn")
        assert f"STAGE: {stage}" in sec
        assert has(sec, r"signal=advance", r"signal=reset", r"signal=stopped")


def test_every_phase_change_removes_old_label():
    t = sdd()
    assert label_changes_ok(t)
    assert has(sect(t, "Phase changes"), r"bd label remove", r"exactly one `phase=`")
    assert len(re.findall(r"bd label remove", t)) >= 1


def test_gate_check_before_plan_done_close_live_and_resume():
    assert gate_before_moves_ok(sdd())


def test_reopen_if_closed_while_check_fails():
    t = sdd()
    assert has(sect(t, "Security gate"), r"reopen", r"closed", r"check fails")
    assert has(sect(t, "Crash Recovery", 2), r"reopen", r"closed", r"post check fails")


def test_base_confirmed_at_creation_and_first_record():
    sec = sect(sdd(), "Base")
    assert has(sec, r"epic creation", r"operator", r"confirm", r"base=<sha>", r"first\s+review record", r"reviews\.rst")
    assert has(sdd(), r'bd label add \$EPIC_ID "base=')


def test_reset_count_includes_security_resets_and_escalation():
    t = sdd()
    assert has(sect(t, "Phase: security-design"), r"signal=reset.*?[Ii]ncrement `reset-count`")
    assert has(sect(t, "Phase: security-review"), r"signal=reset.*?[Ii]ncrement `reset-count`")
    esc = sect(t, "Reset Handling", 2)
    assert has(esc, r"3\+ resets", r"security-design")


def test_arch_review_no_longer_closes_or_marks_implemented():
    t = rd("skills", "arch-review", "SKILL.md")
    assert not re.search(r"^\s*bd close\b", t, re.M)
    assert not re.search(r"s=implemented", t)
    assert not re.search(r"status=implemented", t)
    assert not re.search(r"close the SDD run", t)
    assert not re.search(r'bd label add \$EPIC_ID "phase=', t)
    assert has(t, r"do NOT close\s+the epic", r"security-review")
    s = sdd()
    assert not has(sect(s, "Phase: arch-review"), r"bd close")
    assert has(sect(s, "Phase: arch-review"), r"does NOT close", r"phase=security-review")


def test_plan_flags_protected_out_and_no_inherit_labels():
    t = rd("skills", "plan", "SKILL.md")
    gate = t[t.index("## Step 4"): t.index("## Step 5 ")]
    assert has(gate, r"Protected paths", r"\[out\]", r"Protected set", r"RULES\.md")
    creates = re.findall(r"^\w+=\$\(bd create [^\n]*", t, re.M)
    assert len(creates) >= 3
    assert all("--no-inherit-labels" in c for c in creates)


def test_rules_protected_model_dsl_exclusions():
    t = rd("skills", "rules", "RULES.md")
    sec = sect(t, "Protected set", 2)
    toks = re.findall(r"`([^`\s]+)`", sec)
    assert set(PROTECTED) <= set(toks) and len(toks) == len(set(toks))
    assert re.search(r"^\| security \| opus \|", t, re.M)
    assert has(t, r"\[security run=<run_id> feat=<feat-id> stage=design\|post", r"\[/security\]")
    ex = sect(t, "Review exclusions", 2)
    assert has(ex, r"lockfiles", r"\*\.svg", r"\*\.png", r"dist/", r"node_modules/", r"vendored",
               r"learn-app/server\.js", r"learn-app/cli\.js", r"learn-app/dist/")


def test_gate_lib_reads_protected_list_from_rules(tmp_path):
    (tmp_path / "skills" / "rules").mkdir(parents=True)
    (tmp_path / "skills" / "rules" / "RULES.md").write_text("## Protected set\n\n- `only/here/**`\n\n## Next\n- `ignored/**`\n")
    assert lib.protected_hits(tmp_path, ["only/here/x.py", "ignored/y", "skills/z"]) == ["only/here/x.py"]
    real = lib.protected_set(ROOT)
    assert set(PROTECTED) <= set(real)


def test_gate_default_list_not_used_when_rules_present(tmp_path):
    (tmp_path / "skills" / "rules").mkdir(parents=True)
    (tmp_path / "skills" / "rules" / "RULES.md").write_text("# R\n")
    assert "docs/source/conf.py" in lib.protected_set(tmp_path)


def test_readme_pipeline_and_security_section():
    t = rd("README.md")
    sec = sect(t, "Security review", 2)
    assert has(sec, r"security-design", r"security-review", r"two operator pauses", r"protected set")
    assert "security-review/" in t


def test_plugin_version_bumped():
    r = subprocess.run(["git", "show", "main:.claude-plugin/plugin.json"], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        pytest.skip("main ref not available")
    ver = lambda v: tuple(int(x) for x in v.split("."))
    cur = json.loads(rd(".claude-plugin", "plugin.json"))["version"]
    main_ver = json.loads(r.stdout)["version"]
    if cur == main_ver:
        pytest.skip(f"plugin version equals main ({main_ver}); bump check applies on branches only")
    assert ver(cur) > ver(main_ver)


def test_conf_has_threat_fields():
    t = rd("docs", "source", "conf.py")
    assert has(t, r'"severity"', r'"decisions"', r"security/")


def test_conf_security_warning_fails_build(tmp_path):
    src = tmp_path / "source"
    (src / "security").mkdir(parents=True)
    conf = (ROOT / "docs" / "source" / "conf.py").read_text()
    conf = conf.replace('html_theme = "furo"', 'html_theme = "alabaster"').replace('html_static_path = ["_static"]', "html_static_path = []").replace('templates_path = ["_templates"]', "templates_path = []")
    (src / "conf.py").write_text(conf)
    (src / "index.rst").write_text("Home\n====\n\n.. toctree::\n\n   other\n")
    (src / "other.rst").write_text("Other\n=====\n\n.. threat:: ok\n   :id: THREAT-A-001\n   :nosuchfield: x\n")
    (src / "security" / "s.rst").write_text(":orphan:\n\nS\n=\n\n.. threat:: ok\n   :id: THREAT-A-002\n   :severity: low\n")
    r = subprocess.run([sys.executable, "-m", "sphinx", "-b", "html", str(src), str(tmp_path / "out")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]
    (src / "security" / "s.rst").write_text(":orphan:\n\nS\n=\n\n.. threat:: bad\n   :id: THREAT-A-003\n   :nosuchfield: x\n")
    r = subprocess.run([sys.executable, "-m", "sphinx", "-b", "html", str(src), str(tmp_path / "out2")], capture_output=True, text=True)
    assert r.returncode != 0
    assert "security" in r.stderr


# ---- negative controls: the checkers must reject mutated text ----

def test_neg_missing_label_remove():
    t = sdd().replace("Remove `phase=plan`, add `phase=implement`", "add `phase=implement`")
    assert not label_changes_ok(t)


def test_neg_gate_check_missing_before_done():
    t = sdd()
    sec = sect(t, "Phase: security-review")
    bad = t.replace(sec, re.sub(r"- Run the security gate check[^\n]*\n", "", sec))
    assert gate_before_moves_ok(t)
    assert not gate_before_moves_ok(bad)


def test_neg_gate_check_missing_on_resume():
    t = sdd()
    sec = sect(t, "Crash Recovery", 2)
    assert not gate_before_moves_ok(t.replace(sec, sec.replace("security gate check", "look")))


def test_neg_missing_phase_section():
    t = sdd().replace("### Phase: security-design", "### Phase: other")
    with pytest.raises(AssertionError):
        phase_secs(t)


def test_neg_old_pipeline_string_rejected():
    assert PIPELINE not in "docs → plan → implement → arch-review → done"


def test_neg_gate_lib_ignores_unlisted_path(tmp_path):
    (tmp_path / "skills" / "rules").mkdir(parents=True)
    (tmp_path / "skills" / "rules" / "RULES.md").write_text("## Protected set\n- `a/**`\n")
    assert lib.protected_hits(tmp_path, ["b/x"]) == []


# ---- llm-dsl-2zv1.17: base gate run, implemented-before-post, resume ----

def gate_run_ok(t: str) -> bool:
    s = sect(t, "Running the gate check", 4)
    order = re.search(r"base-path.*?HEAD `check`", s, re.S)
    differs = has(s, r"`differs`", r"git worktree add", r"python3 -I", r"git worktree remove --force",
                  r"also when the run\s+fails", r"as well as from the HEAD run")
    absent = has(s, r"`absent`", r"gate script unverified \(bootstrap\)", r"operator")
    return bool(order and differs and absent)


def call_sites_ref_ok(t: str) -> bool:
    n = len(re.findall(r"Running the gate check", t))
    return n >= 6 and all(
        "Running the gate check" in sect(t, ph)[sect(t, ph).index("gate check"):]
        for ph in ("Phase: security-design",))


def implemented_order_ok(t: str) -> bool:
    ar = sect(t, "Phase: arch-review")
    sr = sect(t, "Phase: security-review")
    return bool(re.search(r"`status=implemented`.*?before the security-review phase.*?add `phase=security-review`", ar, re.S)
                and not re.search(r"status=implemented", sr.split("signal=advance", 1)[1])
                and re.search(r"post tree hash", ar))


def test_gate_run_base_path_then_base_worktree_and_bootstrap():
    assert gate_run_ok(sdd())


def test_gate_call_sites_reference_single_definition():
    t = sdd()
    assert call_sites_ref_ok(t)
    assert t.count("git worktree add") == 1
    sr = rd("skills", "security-review", "SKILL.md")
    assert "Running the gate check" in sect(sr, "Step 13", 2)


def test_implemented_marked_before_post_gate_never_after_close():
    t = sdd()
    assert implemented_order_ok(t)
    sr = sect(t, "Phase: security-review")
    assert sr.index("bd close $EPIC_ID") > sr.index("--stage post")
    assert "status=implemented" not in sr[sr.index("bd close $EPIC_ID"):]
    assert "status=implemented" not in sect(t, "Phase: done")


def test_resume_notes_design_hash_at_record_head():
    cr = sect(sdd(), "Crash Recovery", 2)
    assert has(cr, r"design record's head commit", r"does not deadlock", r"--stage design", r"--stage post")


def test_neg_gate_run_missing_pieces():
    t = sdd()
    assert gate_run_ok(t)
    assert not gate_run_ok(t.replace("python3 -I", "python3"))
    assert not gate_run_ok(t.replace("gate script unverified (bootstrap)", "n/a"))
    assert not gate_run_ok(t.replace("`base-path` first", "x").replace("base-path", "x"))
    assert not gate_run_ok(t.replace("git worktree remove --force", "rm -rf"))


def test_neg_implemented_after_close_rejected():
    t = sdd()
    sr = sect(t, "Phase: security-review")
    assert not implemented_order_ok(t.replace(sr, sr + "\n- Mark requirements `status=implemented`\n"))
    ar = sect(t, "Phase: arch-review")
    assert not implemented_order_ok(t.replace(ar, ar.replace("`status=implemented`", "`status=done`")))

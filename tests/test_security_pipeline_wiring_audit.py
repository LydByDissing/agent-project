# [origin ref=llm-dsl-2zv1.14 req=REQ-SECURITY-REVIEW-006,REQ-SECURITY-REVIEW-003 c4=sdd_skills/sdd_orchestrator]
#   [intent]Audit that no agent following the skills can skip a security phase or end with two phase labels, with scratch-copy breakage proving each guarantee.[/intent]
# [/origin]

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import security_gate_lib as lib  # noqa: E402

pytestmark = pytest.mark.doc_contract

PHASES = ("docs", "security-design", "plan", "implement", "arch-review", "security-review")
EDGES = {
    ("docs", "security-design"), ("security-design", "plan"), ("security-design", "docs"),
    ("plan", "implement"), ("plan", "docs"), ("implement", "arch-review"), ("implement", "docs"),
    ("arch-review", "security-review"), ("arch-review", "docs"),
    ("security-review", "done"), ("security-review", "docs"),
}
GATE = r'security_gate\.py" check'
SPEC_PROTECTED = [
    "docs/source/security/**", "skills/**", ".claude/**", ".claude-plugin/**", "agents/**", "hooks/**",
    "mcp-servers.json", "scripts/security_gate.py", "scripts/security_gate_lib.py", "tests/conftest.py",
    "pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "docs/source/conf.py",
]
SPEC_PROTECTED_TESTS = ["tests/test_security_gate_check.py", "tests/test_security_gate_append_only.py"]


def rd(*p: str, base: Path = ROOT) -> str:
    return base.joinpath(*p).read_text(encoding="utf-8")


def sect(t: str, heading: str, level: int = 3) -> str:
    m = re.search(rf"^{'#' * level} {re.escape(heading)}\b.*$", t, re.M)
    assert m, f"no section {heading}"
    nxt = re.search(rf"^#{{1,{level}}} ", t[m.end():], re.M)
    return t[m.start(): m.end() + nxt.start() if nxt else len(t)]


def skill_files(base: Path = ROOT) -> list[Path]:
    return sorted(base.glob("skills/**/SKILL.md")) + sorted(base.glob("agents/*.md"))


def transitions(sdd: str) -> set[tuple[str, str]]:
    out = set()
    for ph in PHASES:
        sec = sect(sdd, f"Phase: {ph}")
        for ln in sec.splitlines():
            m = re.search(r"[Rr]emove `phase=([a-z-]+)`, add `phase=([a-z-]+)`", ln)
            if m:
                assert m.group(1) == ph, f"{ph} section removes {m.group(1)}"
                out.add((m.group(1), m.group(2)))
            elif re.search(r"add `phase=", ln, re.I):
                raise AssertionError(f"add without remove in {ph}: {ln}")
    return out


def unguarded_adds(files: dict[str, str]) -> list[str]:
    bad = []
    for name, t in files.items():
        lines = t.splitlines()
        for i, ln in enumerate(lines):
            if re.search(r"bd label add\s+\S+\s+\"phase=", ln):
                initial = "feat=" in ln and "run=" in ln
                prev = "\n".join(lines[max(0, i - 2): i])
                if not initial and "bd label remove" not in prev:
                    bad.append(f"{name}:{i + 1}")
            for m in re.finditer(r"add `phase=", ln):
                if not re.search(r"[Rr]emove `phase=[a-z-]+`.*add `phase=", ln):
                    bad.append(f"{name}:{i + 1}")
            if re.search(r"--(add-label|set-labels|labels)[ =].*phase=", ln) and "bd create" not in "\n".join(lines[max(0, i - 3): i + 1]):
                bad.append(f"{name}:{i + 1}")
            if re.search(r"bd update .*--(add-label|set-labels)\S* \S*phase=", ln):
                bad.append(f"{name}:{i + 1}")
    return bad


def texts() -> dict[str, str]:
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in skill_files()}


def epic_closers(files: dict[str, str]) -> list[str]:
    out = []
    for name, t in files.items():
        for i, ln in enumerate(t.splitlines(), 1):
            if re.search(r"bd close\s+(\$EPIC_ID|<epic|\"\$EPIC)", ln) or re.search(r"bd update\s+\$EPIC_ID.*(status[ =]closed|--status closed)", ln):
                out.append(f"{name}:{i}")
    return out


def done_path_ok(sdd: str) -> bool:
    sec = sect(sdd, "Phase: security-review")
    adv = sec[sec.index("signal=advance"):]
    return bool(re.search(GATE.replace(r'security_gate\.py" check', r"security gate check"), adv, re.I)
                and re.search(r"check.*?phase=done.*?check.*?bd close \$EPIC_ID", adv, re.S | re.I))


def resume_ok(sdd: str) -> bool:
    sec = sect(sdd, "Crash Recovery", 2)
    return bool(re.search(r"Before resuming, run the security gate check live", sec)
                and "--stage post" in sec and "--stage design" in sec and re.search(r"never skip", sec))


def sdd() -> str:
    return rd("skills", "sdd", "SKILL.md")


# ---- phase label hygiene ----

def test_sdd_transition_graph_exact():
    assert transitions(sdd()) == EDGES


def test_only_security_review_reaches_done_and_only_security_design_reaches_plan():
    into = {}
    for a, b in transitions(sdd()):
        into.setdefault(b, set()).add(a)
    assert into["done"] == {"security-review"}
    assert into["plan"] == {"security-design"}
    assert into["implement"] == {"plan"}
    assert into["security-review"] == {"arch-review"}
    assert into["security-design"] == {"docs"}


def test_every_phase_label_add_in_all_skills_is_guarded():
    assert unguarded_adds(texts()) == []


def test_enumeration_actually_sees_labels():
    t = texts()
    n = sum(len(re.findall(r"phase=", v)) for v in t.values())
    assert n > 15
    assert "skills/sdd/SKILL.md" in t and "skills/arch-review/SKILL.md" in t and "agents/security-analyst.md" in t


def test_non_sdd_skills_never_touch_epic_phase_label():
    for name, t in texts().items():
        if name.endswith("sdd/SKILL.md"):
            continue
        assert not re.search(r"bd label (add|remove)\s+\S*EPIC\S*\s+\"phase=", t), name
        assert not re.search(r"bd label (add|remove) .*\"phase=", t.replace('"phase=implement', "")), name


def test_neg_unguarded_add_detected():
    f = texts()
    f["skills/sdd/SKILL.md"] = f["skills/sdd/SKILL.md"].replace(
        "- Remove `phase=plan`, add `phase=implement`", "- add `phase=implement`")
    assert unguarded_adds(f)
    g = texts()
    g["skills/arch-review/SKILL.md"] += '\nbd label add $EPIC_ID "phase=reset"\n'
    assert unguarded_adds(g)
    h = texts()
    h["skills/sdd/SKILL.md"] = h["skills/sdd/SKILL.md"].replace('bd label remove $EPIC_ID "phase=$OLD"\n', "")
    assert unguarded_adds(h)


def test_neg_transition_graph_detects_skip():
    t = sdd().replace("- Remove `phase=security-design`, add `phase=plan`", "- Remove `phase=docs`, add `phase=plan`")
    with pytest.raises(AssertionError):
        transitions(t)
    t2 = sdd().replace("Remove `phase=arch-review`, add `phase=security-review`", "Remove `phase=arch-review`, add `phase=done`")
    assert transitions(t2) != EDGES


# ---- epic closing ----

def test_only_sdd_done_path_closes_epic():
    c = epic_closers(texts())
    assert c and all(x.startswith("skills/sdd/SKILL.md") for x in c)
    assert "close the epic" not in rd("skills", "arch-review", "SKILL.md").lower().replace("never close the epic", "").replace("do not close the epic", "").replace("do not close\nthe epic", "")


def test_arch_review_has_no_epic_close_or_implemented():
    t = rd("skills", "arch-review", "SKILL.md")
    assert epic_closers({"a": t}) == []
    assert not re.search(r"status=implemented|s=implemented", t)
    for m in re.finditer(r"mark[^.\n]*implemented", t, re.I):
        assert re.search(r"not|never|no longer", t[max(0, m.start() - 60): m.end()], re.I), m.group(0)


def test_done_path_checks_before_phase_and_close():
    assert done_path_ok(sdd())
    sec = sect(sdd(), "Phase: security-review")
    assert sdd().count("bd close $EPIC_ID") == 1 and "bd close $EPIC_ID" in sec


def test_neg_done_path_without_check():
    t = sdd().replace("- Run the security gate check (`--stage post`, see Running the gate check); it must exit 0\n", "")
    assert not done_path_ok(t)
    t = sdd().replace("- Run the check again (see Running the gate check) immediately before `bd close $EPIC_ID`, then close the epic; no docs edit happens after the close", "- bd close $EPIC_ID")
    assert not done_path_ok(t)


def test_neg_epic_closer_detected():
    f = texts()
    f["skills/arch-review/SKILL.md"] += "\nbd close $EPIC_ID\n"
    assert any(x.startswith("skills/arch-review") for x in epic_closers(f))


# ---- resume ----

def test_resume_reruns_check_both_stages_and_reopens():
    s = sdd()
    assert resume_ok(s)
    assert re.search(r"closed but\s+the post check fails, reopen", sect(s, "Crash Recovery", 2))


def test_neg_resume_without_check():
    s = sdd()
    sec = sect(s, "Crash Recovery", 2)
    assert not resume_ok(s.replace(sec, sec.replace("Before resuming, run the security gate check live", "Before resuming, look around")))
    assert not resume_ok(s.replace(sec, sec.replace("--stage post", "--stage x")))


# ---- resets and escalation ----

def test_security_resets_increment_and_escalate():
    s = sdd()
    for ph in ("security-design", "security-review"):
        sec = sect(s, f"Phase: {ph}")
        reset = sec[sec.index("signal=reset"): sec.index("signal=stopped") if ph == "security-design" else sec.index("signal=stopped")]
        assert "Increment `reset-count`" in reset and "phase=docs" in reset
    esc = sect(s, "Reset Handling", 2)
    assert "security-design and security-review resets" in esc and "3+ resets" in esc


def test_neg_escalation_without_security_counts():
    esc = sect(sdd(), "Reset Handling", 2)
    assert "security-design and security-review resets" not in esc.replace("security-design and security-review resets", "")


def test_req012_limits_referenced_and_operator_confirmed():
    s = sdd() + rd("skills", "security-review", "SKILL.md")
    sec = sect(rd("skills", "security-review", "SKILL.md"), "Step 10", 2)
    assert re.search(r"\*\*2\*\* `security-design` resets", sec) and re.search(r"\*\*3\*\* fix rounds", sec)
    assert "AskUserQuestion" in sec and re.search(r"explicit \"yes\"", sec) and "stop" in sec
    assert re.search(r"2 design resets / 3 fix rounds", s)


def test_sdd_defers_limits_to_security_review():
    # sdd itself says nothing about the 2-reset / 3-fix-round pause; only the delegated skill does
    sec = sdd()
    assert "skills/security-review/SKILL.md" in sec
    assert not re.search(r"fix round|2 design resets|2 security-design resets", sec)


# ---- RULES / protected set ----

def test_rules_protected_set_equals_spec_list():
    real = set(lib.protected_set(ROOT))
    assert set(SPEC_PROTECTED) <= real
    extra = real - set(SPEC_PROTECTED) - {"tests/test_security_gate*.py", "tests/test_*append_only*.py"}
    assert extra == set(), f"undocumented extras: {extra}"


def test_protected_set_covers_gate_tests():
    hits = lib.protected_hits(ROOT, SPEC_PROTECTED_TESTS)
    assert hits == SPEC_PROTECTED_TESTS


def test_lib_fallback_protects_gate_tests(tmp_path):
    assert "tests/test_security_gate*.py" in lib.protected_set(tmp_path)


def test_security_review_reads_rules_exclusions_and_protected():
    t = rd("skills", "security-review", "SKILL.md")
    assert re.search(r"Exclusion list.*default list in `skills/rules/RULES\.md`", t, re.S)
    assert "(`skills/rules/RULES.md` defines the set)" in t
    r = rd("skills", "rules", "RULES.md")
    ex = sect(r, "Review exclusions", 2)
    for tok in ("lockfiles", "*.svg", "*.png", "dist/", "node_modules/", "learn-app/server.js", "learn-app/cli.js", "learn-app/dist/"):
        assert tok in ex


def test_neg_protected_parse_drops_removed_entry(tmp_path):
    (tmp_path / "skills" / "rules").mkdir(parents=True)
    t = rd("skills", "rules", "RULES.md").replace("- `skills/**`\n", "")
    (tmp_path / "skills" / "rules" / "RULES.md").write_text(t)
    assert "skills/**" not in lib.protected_set(tmp_path)
    assert lib.protected_hits(tmp_path, ["skills/x/SKILL.md"]) == []


# ---- conf.py ----

def _build(tmp_path: Path, security: str, other: str, tag: str) -> subprocess.CompletedProcess:
    src = tmp_path / f"src{tag}"
    (src / "security").mkdir(parents=True)
    conf = rd("docs", "source", "conf.py")
    conf = conf.replace('html_theme = "furo"', 'html_theme = "alabaster"').replace('html_static_path = ["_static"]', "html_static_path = []").replace('templates_path = ["_templates"]', "templates_path = []")
    (src / "conf.py").write_text(conf)
    (src / "index.rst").write_text("Home\n====\n\n.. toctree::\n\n   other\n   security/s\n")
    (src / "other.rst").write_text(other)
    (src / "security" / "s.rst").write_text(security)
    return subprocess.run([sys.executable, "-m", "sphinx", "-b", "html", str(src), str(tmp_path / f"out{tag}")], capture_output=True, text=True)


GOOD_SEC = "S\n=\n\n.. threat:: ok\n   :id: THREAT-A-002\n   :severity: high\n   :decisions: d1\n   :stride: T\n   :decided_by: operator\n"
BAD_SEC = "S\n=\n\n.. threat:: bad\n   :id: THREAT-A-003\n   :nosuchfield: x\n"
GOOD_OTHER = "Other\n=====\n\n.. req:: fine\n   :id: REQ-A-001\n"
BAD_OTHER = "Other\n=====\n\n.. req:: weird\n   :id: REQ-A-001\n   :nosuchfield: x\n"


def test_conf_security_ok_other_ok(tmp_path):
    r = _build(tmp_path, GOOD_SEC, GOOD_OTHER, "a")
    assert r.returncode == 0, r.stderr[-800:]
    assert "WARNING" not in r.stderr


def test_conf_warning_elsewhere_passes(tmp_path):
    r = _build(tmp_path, GOOD_SEC, BAD_OTHER, "b")
    assert r.returncode == 0, r.stderr[-800:]
    assert "WARNING" in r.stderr


def test_conf_warning_under_security_fails(tmp_path):
    r = _build(tmp_path, BAD_SEC, GOOD_OTHER, "c")
    assert r.returncode != 0
    assert "security" in r.stderr


def test_conf_neg_hook_removed_lets_security_warning_pass(tmp_path):
    src = tmp_path / "srcd"
    (src / "security").mkdir(parents=True)
    conf = rd("docs", "source", "conf.py").split("import logging")[0]
    conf = conf.replace('html_theme = "furo"', 'html_theme = "alabaster"').replace('html_static_path = ["_static"]', "html_static_path = []").replace('templates_path = ["_templates"]', "templates_path = []")
    (src / "conf.py").write_text(conf)
    (src / "index.rst").write_text("Home\n====\n\n.. toctree::\n\n   security/s\n")
    (src / "security" / "s.rst").write_text(BAD_SEC)
    r = subprocess.run([sys.executable, "-m", "sphinx", "-b", "html", str(src), str(tmp_path / "outd")], capture_output=True, text=True)
    assert r.returncode == 0 and "WARNING" in r.stderr


# ---- plan ----

def task_creates(t: str) -> list[str]:
    cs = re.findall(r"bd create [^\n]*(?:\\\n[^\n]*)*", t)
    return [c for c in cs if re.search(r"--(silent|labels)", c)]


def test_plan_every_bd_create_no_inherit_and_flag_reads_rules():
    t = rd("skills", "plan", "SKILL.md")
    assert len(task_creates(t)) >= 3
    assert all("--no-inherit-labels" in c for c in task_creates(t)), task_creates(t)
    gate = t[t.index("## Step 4"): t.index("## Step 5 ")]
    assert re.search(r"Protected set.*RULES\.md|RULES\.md.*Protected set", gate, re.S) and "[out]" in gate


def test_neg_plan_missing_no_inherit_detected():
    t = rd("skills", "plan", "SKILL.md").replace('--silent --no-inherit-labels', '--silent', 1)
    assert not all("--no-inherit-labels" in c for c in task_creates(t))


# ---- README / plugin ----

def test_readme_two_pauses_and_exact_pipeline():
    t = rd("README.md")
    pipe = "docs → security-design → plan → implement → arch-review → security-review → done"
    assert t.count(pipe) >= 1
    assert re.search(r"two\s+security-review pauses", t) or re.search(r"two\s+operator\s+pauses", t)
    sec = sect(t, "Security review", 2)
    assert re.search(r"two\s+operator\s+pauses", sec)
    assert "`security-design`" in sec and "`security-review`" in sec


def test_neg_readme_old_pipeline_not_accepted():
    t = rd("README.md").replace("security-design → ", "")
    assert "docs → security-design → plan" not in t


def _ver(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in s.split("."))


def test_plugin_version_strictly_above_main():
    cur = json.loads(rd(".claude-plugin", "plugin.json"))["version"]
    r = subprocess.run(["git", "show", "main:.claude-plugin/plugin.json"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("no main branch")
    assert _ver(cur) > _ver(json.loads(r.stdout)["version"])


def test_version_compare_is_numeric_not_lexical():
    assert _ver("2.10.0") > _ver("2.9.0") and not _ver("2.3.3") > _ver("2.3.3")


# ---- scratch-copy breakage of the real checkers ----

def test_scratch_copy_breakage_end_to_end(tmp_path):
    for p in skill_files():
        dst = tmp_path / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, dst)
    s = tmp_path / "skills" / "sdd" / "SKILL.md"
    clean = {str(p.relative_to(tmp_path)): p.read_text() for p in skill_files(tmp_path)}
    assert unguarded_adds(clean) == [] and epic_closers(clean) and done_path_ok(s.read_text())
    s.write_text(s.read_text().replace("Remove `phase=implement`, add `phase=arch-review`", "add `phase=arch-review`"))
    broken = {str(p.relative_to(tmp_path)): p.read_text() for p in skill_files(tmp_path)}
    assert unguarded_adds(broken)


# ---- tests that cannot fail in the coder's file ----

def test_coder_file_label_checker_is_weak():
    # coder's label_changes_ok only inspects lines containing 'add `phase=' inside phase sections: an
    # unguarded 'bd label add' in the State block or another skill is invisible to it; ours sees it.
    f = texts()
    f["skills/conductor/SKILL.md"] += '\nbd label add $EPIC_ID "phase=done"\n'
    assert unguarded_adds(f)

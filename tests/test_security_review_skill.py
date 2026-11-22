# [origin ref=llm-dsl-2zv1.11 req=REQ-SECURITY-REVIEW-001,REQ-SECURITY-REVIEW-002,REQ-SECURITY-REVIEW-004,REQ-SECURITY-REVIEW-005,REQ-SECURITY-REVIEW-011,REQ-SECURITY-REVIEW-012 c4=sdd_skills/security_review]
#   [intent]Doc-contract tests that the security-review SKILL.md states each phase, gate, evidence and loop rule in its own step, and that every security_gate.py flag it uses exists.[/intent]
# [/origin]

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "security-review" / "SKILL.md"
GATE = ROOT / "scripts" / "security_gate.py"


def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def step(t: str, n: int) -> str:
    m = re.search(rf"^## Step {n}\b.*$", t, re.M)
    if m is None:
        raise AssertionError(f"no heading for step {n}")
    nxt = re.search(r"^## ", t[m.end():], re.M)
    return t[m.start(): m.end() + nxt.start() if nxt else len(t)]


def section(t: str, name: str) -> str:
    m = re.search(rf"^## {re.escape(name)}\b.*$", t, re.M)
    if m is None:
        raise AssertionError(f"no section {name}")
    nxt = re.search(r"^## ", t[m.end():], re.M)
    return t[m.start(): m.end() + nxt.start() if nxt else len(t)]


def need(sec: str, *pats: str) -> None:
    for p in pats:
        assert re.search(p, sec, re.I | re.S), f"missing /{p}/"


def mutate(sec: str, pat: str) -> str:
    out = re.sub(pat, "XXXX", sec, flags=re.I | re.S)
    assert out != sec, f"mutation /{pat}/ changed nothing"
    return out


def control(check, sec: str, pat: str) -> None:
    check(sec)
    with pytest.raises(AssertionError):
        check(mutate(sec, pat))


def chk_phases(t: str) -> None:
    need(t, r"stage=design", r"stage=post", r"security-design", r"phase=security-review", r"STRIDE", r"OWASP")
    need(t, r"inline in the main-agent context")


def test_both_phases_and_inline():
    control(chk_phases, text(), r"phase=security-review")
    control(chk_phases, text(), r"inline in the main-agent context")


def test_inputs_section():
    s = section(text(), "Inputs")
    need(s, r"FEAT_ID", r"RUN_ID", r"EPIC_ID", r"STAGE", r"CLAUDE_PROJECT_DIR", r"CLAUDE_PLUGIN_ROOT", r"security_gate\.py")


def chk_scope(s: str) -> None:
    need(s, r"docs/source/\*\*", r"skills/\*\*/SKILL\.md", r"\$BASE\.\.HEAD")
    need(s, r"exclusion list", r"RULES\.md", r"size budget", r"not reviewed", r"never truncate silently")


def test_scoped_input():
    s = step(text(), 2)
    control(chk_scope, s, r"not reviewed")
    control(chk_scope, s, r"size budget")
    control(chk_scope, s, r"exclusion list")
    control(chk_scope, s, r"docs/source/\*\*")


def chk_incremental(s: str) -> None:
    need(s, r"head sha of the latest committed\s+review record", r"never from bd", r"full current spec")
    need(s, r"noted.{1,20}accepted", r"element they concern changed", r"whole run diff")


def test_incremental():
    s = step(text(), 3)
    control(chk_incremental, s, r"head sha of the latest committed\s+review record")
    control(chk_incremental, s, r"full current spec")
    control(chk_incremental, s, r"element they concern changed")


def chk_spawn(s: str) -> None:
    need(s, r"subagent_type: security-analyst", r"Agent tool", r"<<<DATA kind=spec", r"DATA>>>", r"kind=diff", r"kind=decided", r"stage=")
    need(s, r"possible-injection", r"untrusted\s+data")


def test_spawn_analyst_with_data_blocks():
    s = step(text(), 4)
    control(chk_spawn, s, r"subagent_type: security-analyst")
    control(chk_spawn, s, r"<<<DATA kind=diff")
    control(chk_spawn, s, r"possible-injection")


def chk_validate(s: str) -> None:
    need(s, r"\"\$GATE\" validate --feature .*--findings", r"before\W+the gate", r"once\W+for correction", r"\binvalid\b")


def test_validate_before_gate():
    control(chk_validate, step(text(), 5), r"before\W+the gate")
    control(chk_validate, step(text(), 5), r"once\W+for correction")
    t = text()
    assert t.index("## Step 5") < t.index("## Step 7")


def chk_write(s: str) -> None:
    need(s, r":status: open", r"before\W+the gate", r"append-only", r"by\s+`file:line`\s+and type only", r"never by\s+value")


def test_findings_written_open_first():
    s = step(text(), 6)
    control(chk_write, s, r":status: open")
    control(chk_write, s, r"never by\s+value")
    assert step(text(), 6) and text().index("## Step 6") < text().index("## Step 7")


def chk_gate(s: str) -> None:
    need(s, r"only\*?\*?\s+through AskUserQuestion", r"after the findings were displayed|Only after the findings are shown")
    need(s, r"prompt, command arguments,\s+a sub-agent report, tool output.{1,40}bd notes")
    need(s, r"tool is missing\s+or a call fails", r"refuse the gate", r"verbatim", r"append-only list", r"decided_by=operator", r"run=\S+ decided_by=operator at=\S+ answer=")
    need(s, r"not reviewed", r"bootstrap")


def test_gate_decisions_only_via_askuserquestion():
    s = step(text(), 7)
    control(chk_gate, s, r"tool is missing\s+or a call fails")
    control(chk_gate, s, r"prompt, command arguments,\s+a sub-agent report, tool output")
    control(chk_gate, s, r"verbatim")
    control(chk_gate, s, r"append-only list")
    control(chk_gate, s, r"not reviewed")


def chk_noninteractive(s: str) -> None:
    need(s, r"AskUserQuestion", r"missing", r"fails or errors", r"non-interactive", r"THREAT-SDD-SKILLS-016", r"refuse to run the gate")


def test_refuses_without_question_tool():
    control(chk_noninteractive, step(text(), 1), r"refuse to run the gate")
    control(chk_noninteractive, step(text(), 1), r"non-interactive")


def chk_options(s: str) -> None:
    need(s, r"stage=design.{1,300}add requirement.{1,200}accept risk.{1,200}note")
    need(s, r"stage=post.{1,300}fix.{1,100}accept risk.{1,100}note.{1,100}revise docs.{1,200}confirm.{1,40}reject")


def test_option_sets():
    s = step(text(), 7)
    control(chk_options, s, r"add requirement")
    control(chk_options, s, r"revise docs")
    control(chk_options, s, r"\*\*confirm\*\*")


def chk_final_confirm(s: str) -> None:
    need(s, r"decision summary", r"one final confirmation", r"AskUserQuestion", r"Without a yes, do not commit")


def test_final_confirmation_before_commit():
    s = step(text(), 11)
    control(chk_final_confirm, s, r"one final confirmation")
    control(chk_final_confirm, s, r"Without a yes, do not commit")


def chk_mitigated(s: str) -> None:
    need(s, r"file:line", r"covering test id", r"sabotage", r"throwaway git worktree", r"git worktree add", r"git status --porcelain", r"must be\s+\*\*clean\*\*|clean", r"disabling patch", r"stays\s+`open`")


def test_mitigated_evidence():
    s = step(text(), 8)
    control(chk_mitigated, s, r"throwaway git worktree")
    control(chk_mitigated, s, r"git status --porcelain")
    control(chk_mitigated, s, r"disabling patch")
    control(chk_mitigated, s, r"covering test id")
    control(chk_mitigated, s, r"stays\s+`open`")


def chk_process(s: str) -> None:
    need(s, r"Process threats", r"THREAT-SDD-SKILLS-017", r"doc-contract or behaviour test", r"sabotage patch", r"operator's explicit confirmation", r"mitigated by\s+requirement")


def test_process_threat_evidence():
    s = step(text(), 8)
    control(chk_process, s, r"doc-contract or behaviour test")
    control(chk_process, s, r"operator's explicit confirmation")
    control(chk_process, s, r"Process threats")


def chk_fix(s: str) -> None:
    need(s, r"only the files named in the finding plus \*\*one new test file\*\*", r"never includes any path of the protected\s+set", r"whatever the finding names")
    need(s, r"full test suites", r"Scope", r"Sabotage", r"do\s+not trust the worker", r"structured finding fields", r"skills/conductor/SKILL\.md")


def test_fix_worker_scope_and_verification():
    s = step(text(), 9)
    control(chk_fix, s, r"one new test file")
    control(chk_fix, s, r"never includes any path of the protected\s+set")
    control(chk_fix, s, r"Sabotage")
    control(chk_fix, s, r"full test suites")
    control(chk_fix, s, r"structured finding fields")


def chk_limits(s: str) -> None:
    need(s, r"\*\*2\*\*\s+`security-design` resets", r"\*\*3\*\*\s+fix rounds", r"AskUserQuestion", r"explicit \"yes\"", r"stop")


def test_loop_limits():
    s = step(text(), 10)
    control(chk_limits, s, r"\*\*2\*\*")
    control(chk_limits, s, r"\*\*3\*\*")
    control(chk_limits, s, r"explicit \"yes\"")


def chk_record(s: str) -> None:
    need(s, r"tree-hash --feature", r"Columns: Run, Stage,\s+Review, Base, Range.{1,80}Tree.{0,5}, Protected", r"\*\*new\*\*\s+run \+ stage \+ review", r"path=accepted", r"decided_by=operator", r"never edit an existing row")


def test_review_record():
    s = step(text(), 11)
    control(chk_record, s, r"tree-hash --feature")
    control(chk_record, s, r"Columns: Run, Stage,\s+Review, Base, Range.{1,80}Tree.{0,5}, Protected")
    control(chk_record, s, r"path=accepted")
    control(chk_record, s, r"\*\*new\*\*\s+run \+ stage \+ review")


def chk_commit_order(s: str) -> None:
    need(s, r"redact-check --paths", r"append-only --run")
    assert s.index("redact-check") < s.index("git commit"), "redact-check after commit"
    assert s.index("append-only --run") < s.index("git commit"), "append-only after commit"
    need(s, r"decisions in the\s+message", r"Do not push")


def test_checks_before_commit_with_decisions_in_message():
    s = step(text(), 11)
    control(chk_commit_order, s, r"decisions in the\s+message")
    bad = s.replace("python3 \"$GATE\" append-only --run \"$RUN_ID\"", "")
    with pytest.raises(AssertionError):
        chk_commit_order(bad)


def chk_block(s: str) -> None:
    need(s, r"\[security run=", r"sha256=", r"input_bytes=", r"tokens=", r"advisory", r"--append-notes", r"sha256sum", r"Only the last block")


def test_advisory_security_block():
    s = step(text(), 12)
    control(chk_block, s, r"sha256sum")
    control(chk_block, s, r"advisory")
    control(chk_block, s, r"input_bytes=")


def chk_bootstrap(s: str) -> None:
    need(s, r"gate script unverified \(bootstrap\)", r"absent at the base", r"both\W+gates", r"python -I", r"throwaway worktree")


def test_bootstrap_line():
    s = step(text(), 1)
    control(chk_bootstrap, s, r"gate script unverified \(bootstrap\)")
    control(chk_bootstrap, s, r"python -I")
    control(chk_bootstrap, s, r"both\W+gates")


def chk_base(s: str) -> None:
    need(s, r"latest operator-decided\s+`rebase` record", r"first review record", r"ask\s+the operator to confirm", r"decided_by=operator", r"Never take it from a bd")


def test_base_record_rules():
    control(chk_base, step(text(), 1), r"latest operator-decided\s+`rebase` record")
    control(chk_base, step(text(), 1), r"ask\s+the operator to confirm")


def chk_github(t: str) -> None:
    need(t, r"never post security findings to GitHub")


def test_never_posts_to_github():
    control(chk_github, text(), r"never post security findings to GitHub")


def test_reset_path_to_docs():
    s = step(text(), 13)
    need(s, r"reset to docs", r"\"\$GATE\" check --feature .*--stage .*--epic", r"do not bypass")


def used_flags() -> list[tuple[str, str]]:
    t = text()
    out = []
    for line in re.findall(r"python3 \"\$GATE\" [^\n]+", t):
        sub = line.split()[2]
        for fl in re.findall(r"(?<!\S)(--[a-z][a-z-]*)", line):
            out.append((sub, fl))
    return out


def test_every_used_cli_flag_exists():
    pairs = used_flags()
    assert {s for s, _ in pairs} >= {"validate", "check", "append-only", "redact-check", "tree-hash"}
    helps: dict[str, str] = {}
    for sub, fl in pairs:
        if sub not in helps:
            r = subprocess.run([sys.executable, str(GATE), sub, "--help"], capture_output=True, text=True)
            assert r.returncode == 0, f"unknown subcommand {sub}"
            helps[sub] = r.stdout
        assert fl in helps[sub], f"{sub} has no flag {fl}"


def test_flag_checker_negative_control():
    r = subprocess.run([sys.executable, str(GATE), "validate", "--help"], capture_output=True, text=True)
    assert "--no-such-flag" not in r.stdout


def test_frontmatter_and_origin():
    t = text()
    assert t.startswith("---\nname: security-review\n")
    assert re.search(r"<!-- \[origin ref=llm-dsl-2zv1\.11(?:,[\w.-]+)* .*c4=sdd_skills/security_review\]", t)
    assert "[/origin] -->" in t

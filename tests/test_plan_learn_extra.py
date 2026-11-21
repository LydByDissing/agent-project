# [origin ref=llm-dsl-gu1y.18,llm-dsl-gu1y.14 req=REQ-OPERATOR-EDU-004 c4=sdd_skills/plan_skill]
#   [intent]Audits the plan skill lesson-preparation instructions, the --dir and --docs-dir render modes of generate_diagrams.py, the plugin version bump and the repo learn/ validation against the t7 acceptance criteria[/intent]
# [/origin]

import json
import re
import shutil
import subprocess

import pytest

from tests._learn_helpers import (
    BANNER_TEXT,
    PUML_BROKEN,
    PUML_DEPRECATED,
    PUML_DEPRECATED_LABEL,
    PUML_NAME_MISMATCH,
    PUML_OK,
    ROOT,
    heading_pos,
    needs_plantuml,
    out,
    plan_text,
    run_diagrams,
    step_section,
    svg_text_nodes,
    write_file,
)

PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
LEARN = ROOT / "learn"
SEED_PUML = LEARN / "backend" / "http-caching" / "diagrams" / "revalidation.puml"


def _job_line(section: str, bd_id: str) -> str:
    m = re.search(rf"^\[job\s+id=<{bd_id}>.*\]$", section, re.M)
    assert m is not None, f"Step 6 exec example has no job line for <{bd_id}>"
    return m.group(0)


def _single_bump(base: str, cur: str) -> bool:
    b = [int(x) for x in base.split(".")]
    c = [int(x) for x in cur.split(".")]
    i = next((k for k in range(3) if b[k] != c[k]), None)
    return i is not None and c[i] == b[i] + 1 and all(v == 0 for v in c[i + 1 :])


def test_docs_dir_missing_diagrams_folder_exits_one(tmp_path):
    docs = tmp_path / "docs" / "source"
    docs.mkdir(parents=True)

    r = run_diagrams(["--docs-dir", str(docs)])

    assert r.returncode == 1, out(r)
    assert "Diagrams directory not found" in out(r)
    assert "bootstrap_sphinx.py" in out(r)


def test_docs_dir_empty_diagrams_folder_exits_zero(tmp_path):
    diag = tmp_path / "docs" / "source" / "architecture" / "diagrams"
    diag.mkdir(parents=True)

    r = run_diagrams(["--docs-dir", str(tmp_path / "docs" / "source")])

    assert r.returncode == 0, out(r)
    assert "No .puml files found" in out(r)


@needs_plantuml
def test_docs_dir_renders_deprecated_source_without_warning_gate(tmp_path):
    docs = tmp_path / "docs" / "source"
    diag = docs / "architecture" / "diagrams"
    src = write_file(diag / "fx_dep.puml", PUML_DEPRECATED)

    r = run_diagrams(["--docs-dir", str(docs)])

    assert r.returncode == 0, out(r)
    assert "PlantUML warning" not in out(r)
    assert "1 rendered, 0 failed." in out(r)
    svg = src.with_suffix(".svg")
    assert svg.exists(), out(r)
    texts = svg_text_nodes(svg)
    assert any(t.startswith(BANNER_TEXT) for t in texts), (
        f"fixture no longer triggers the PlantUML banner {BANNER_TEXT!r}, so the no-gate assertion proves nothing; "
        f"text nodes: {texts[:5]}"
    )


@needs_plantuml
def test_docs_dir_renders_clean_source_next_to_source_file(tmp_path):
    docs = tmp_path / "docs" / "source"
    diag = docs / "architecture" / "diagrams"
    src = write_file(diag / "fx_ok.puml", PUML_OK)

    r = run_diagrams(["--docs-dir", str(docs)])

    assert r.returncode == 0, out(r)
    assert src.with_suffix(".svg").exists()
    assert "1 rendered, 0 failed." in out(r)


@needs_plantuml
def test_dir_renders_two_levels_deep_each_beside_its_source(tmp_path):
    top = write_file(tmp_path / "lesson" / "diagrams" / "fx_ok.puml", PUML_OK)
    deep = write_file(
        tmp_path / "lesson" / "sub" / "nested" / "diagrams" / "fx_deep.puml",
        PUML_OK.replace("fx_ok", "fx_deep"),
    )

    r = run_diagrams(["--dir", str(tmp_path)])

    assert r.returncode == 0, out(r)
    assert top.with_suffix(".svg").exists(), out(r)
    assert deep.with_suffix(".svg").exists(), out(r)
    assert "Rendering 2 diagram(s)" in out(r)
    assert "2 rendered, 0 failed." in out(r)


@needs_plantuml
def test_dir_ignores_non_puml_files(tmp_path):
    src = write_file(tmp_path / "lesson" / "diagrams" / "fx_ok.puml", PUML_OK)
    notes = write_file(tmp_path / "lesson" / "notes.md", "# not a diagram\n")
    txt = write_file(tmp_path / "lesson" / "diagrams" / "readme.txt", "plain text\n")
    bak = write_file(tmp_path / "lesson" / "diagrams" / "old.puml.bak", PUML_DEPRECATED)
    notes_before = notes.read_text()
    txt_before = txt.read_text()

    r = run_diagrams(["--dir", str(tmp_path)])

    assert r.returncode == 0, out(r)
    assert "Rendering 1 diagram(s)" in out(r)
    assert src.with_suffix(".svg").exists()
    assert not notes.with_suffix(".svg").exists()
    assert not txt.with_suffix(".svg").exists()
    assert not bak.with_name("old.puml.svg").exists()
    assert notes.read_text() == notes_before
    assert txt.read_text() == txt_before


@needs_plantuml
def test_dir_mixed_ok_and_deprecated_exits_one_and_names_failing_file(tmp_path):
    ok = write_file(tmp_path / "lesson" / "diagrams" / "fx_ok.puml", PUML_OK)
    dep = write_file(tmp_path / "lesson" / "diagrams" / "fx_dep.puml", PUML_DEPRECATED)

    r = run_diagrams(["--dir", str(tmp_path)])

    assert r.returncode == 1, out(r)
    assert f"ERROR  {dep}" in r.stdout, r.stdout
    assert f"OK     {ok}" in r.stdout, r.stdout
    assert "PlantUML warning in fx_dep.svg" in r.stdout
    assert "1 rendered, 1 failed." in r.stdout


@needs_plantuml
def test_dir_name_mismatch_exits_one_and_names_expected_svg(tmp_path):
    mis = write_file(tmp_path / "lesson" / "diagrams" / "fx_mis.puml", PUML_NAME_MISMATCH)

    r = run_diagrams(["--dir", str(tmp_path)])

    assert r.returncode == 1, out(r)
    assert f"ERROR  {mis}" in r.stdout, r.stdout
    assert "expected fx_mis.svg next to source" in r.stdout
    assert not mis.with_suffix(".svg").exists()


@needs_plantuml
def test_dir_broken_syntax_exits_one_and_names_failing_file(tmp_path):
    bad = write_file(tmp_path / "lesson" / "diagrams" / "fx_bad.puml", PUML_BROKEN)

    r = run_diagrams(["--dir", str(tmp_path)])

    assert r.returncode == 1, out(r)
    assert str(bad) in out(r), out(r)
    assert "1 failed." in r.stdout


@needs_plantuml
def test_dir_clean_fixture_raises_no_false_positive_warning(tmp_path):
    src = write_file(tmp_path / "lesson" / "diagrams" / "fx_ok.puml", PUML_OK)

    r = run_diagrams(["--dir", str(tmp_path)])

    assert r.returncode == 0, out(r)
    assert "PlantUML warning" not in out(r)
    assert "ERROR" not in out(r)
    assert src.with_suffix(".svg").exists()
    assert "1 rendered, 0 failed." in r.stdout


@needs_plantuml
def test_dir_copy_of_seed_lesson_renders_without_warning(tmp_path):
    assert SEED_PUML.exists()
    copy = tmp_path / "learn" / "backend" / "http-caching" / "diagrams" / "revalidation.puml"
    write_file(copy, SEED_PUML.read_text())

    r = run_diagrams(["--dir", str(tmp_path / "learn")])

    assert r.returncode == 0, out(r)
    assert "PlantUML warning" not in out(r)
    assert copy.with_suffix(".svg").exists()


@needs_plantuml
def test_dir_label_containing_word_deprecated_is_not_flagged(tmp_path):
    src = write_file(tmp_path / "lesson" / "diagrams" / "lbl_ok.puml", PUML_DEPRECATED_LABEL)

    r = run_diagrams(["--dir", str(tmp_path)])

    assert r.returncode == 0, out(r)
    assert src.with_suffix(".svg").exists()


@pytest.mark.doc_contract
class TestPlanSkillExecExample:
    def test_coder_job_line_carries_model_and_topics(self):
        line = _job_line(step_section(plan_text(), "6"), "BD_CODER")
        assert re.search(r"\brole=coder\b", line)
        assert re.search(r"\bmodel=haiku\|sonnet\b", line)
        assert re.search(r"\btopics=iac/terraform-state\b", line)

    def test_tester_job_line_carries_depends_and_topics(self):
        line = _job_line(step_section(plan_text(), "6"), "BD_TESTER")
        assert re.search(r"\brole=tester\b", line)
        assert re.search(r"\bdepends=<BD_CODER>", line)
        assert re.search(r"\btopics=iac/terraform-state\b", line)

    def test_reviewer_job_line_has_depends_and_no_topics(self):
        line = _job_line(step_section(plan_text(), "6"), "BD_REVIEWER")
        assert re.search(r"\brole=reviewer\b", line)
        assert re.search(r"\bdepends=<BD_CODER>", line)
        assert "topics=" not in line


@pytest.mark.doc_contract
class TestPlanSkillLessonStep:

    def test_topic_entry_overrides_domain_interest(self):
        sec = step_section(plan_text(), "5b")
        assert re.search(r"topic\s+entry\s+overrides\s+its\s+domain", sec, re.I)

    def test_learn_home_defaults_to_home_sdd(self):
        assert re.search(r'LEARN_HOME="\$\{SDD_LEARN_HOME:-\$HOME/\.sdd\}"', step_section(plan_text(), "5b"))

    def test_render_step_uses_plugin_root_path(self):
        sec = step_section(plan_text(), "5b")
        assert re.search(
            r'python3?\s+"\$\{CLAUDE_PLUGIN_ROOT\}/skills/docs/scripts/generate_diagrams\.py"\s+--dir\s+"\$CLAUDE_PROJECT_DIR/learn"',
            sec,
        )

    def test_validate_step_uses_plugin_root_path(self):
        sec = step_section(plan_text(), "5b")
        assert re.search(
            r'node\s+"\$\{CLAUDE_PLUGIN_ROOT\}/learn-app/cli\.js"\s+validate\s+--project\s+"\$CLAUDE_PROJECT_DIR"',
            sec,
        )

    def test_lesson_front_matter_requires_id_title_level_requires_sources_updated(self):
        sec = step_section(plan_text(), "5b")
        assert re.search(r"\bid:\s*<domain>/<topic>/<NN>-<slug>", sec)
        assert re.search(r"`title`", sec)
        assert re.search(r"`level`", sec)
        assert re.search(r"`requires:`", sec)
        assert re.search(r"`sources:`\s*\(at least one entry", sec)
        assert re.search(r"`updated:`[^\n]*date\s+\+%F", sec)

    def test_lesson_step_never_blocks_the_plan_gate(self):
        sec = step_section(plan_text(), "5b")
        assert re.search(r"never\s+asks\s+the\s+operator\s+a\s+question", sec, re.I)
        assert re.search(r"never\s+blocks\s+the\s+plan", sec, re.I)

    def test_lesson_step_runs_after_confirm_gate_and_bd_creation(self):
        text = plan_text()
        gate, create, lesson, handoff = (heading_pos(text, s) for s in ("4", "5", "5b", "6"))
        assert gate < create < lesson < handoff

    def test_lesson_failure_is_recorded_as_bd_note_and_plan_continues(self):
        sec = step_section(plan_text(), "5b")
        assert re.search(r"record\s+the\s+topic\s+as\s+a\s+bd\s+note\s+on\s+the\s+plan\s+epic", sec)
        assert re.search(r"and\s+continue\b", sec)

    def test_lesson_step_generates_no_quiz_and_never_writes_docs(self):
        sec = step_section(plan_text(), "5b")
        assert re.search(r"No\s+quiz\s+questions\s+are\s+generated\s+here", sec)
        assert re.search(r"Lessons\s+never\s+go\s+under\s+`docs/`", sec)


    def test_plan_has_no_project_relative_render_path(self):
        assert not re.search(r"python3?\s+skills/docs/scripts/generate_diagrams\.py", plan_text())


def test_every_learn_puml_has_svg_beside_it_named_after_its_stem():
    pumls = sorted(LEARN.rglob("*.puml"))
    assert len(pumls) >= 1, "expected at least one lesson diagram under learn/"
    for puml in pumls:
        svg = puml.with_suffix(".svg")
        assert svg.exists(), f"missing {svg.relative_to(ROOT)}"
        assert f"@startuml {puml.stem}" in puml.read_text(), (
            f"{puml.relative_to(ROOT)} must name its @startuml block after the file stem"
        )


@pytest.mark.parametrize(
    ("base", "cur", "ok"),
    [
        ("2.2.0", "2.3.0", True),
        ("2.2.0", "2.2.1", True),
        ("2.2.9", "3.0.0", True),
        ("2.2.0", "2.4.0", False),
        ("2.2.0", "2.3.1", False),
        ("2.2.0", "2.2.0", False),
    ],
)
def test_single_bump_rule_accepts_exactly_one_increment(base, cur, ok):
    assert _single_bump(base, cur) is ok


def test_plugin_version_is_higher_than_main():
    try:
        base = subprocess.run(
            ["git", "show", "main:.claude-plugin/plugin.json"],
            capture_output=True, text=True, cwd=ROOT, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("main ref with .claude-plugin/plugin.json not available; single-bump check not run")
    base_ver = json.loads(base)["version"]
    cur_ver = json.loads(PLUGIN_JSON.read_text())["version"]
    if base_ver == cur_ver:
        pytest.skip(f"plugin version equals main ({base_ver}); single-bump check not applicable")
    as_tuple = lambda v: tuple(int(x) for x in v.split("."))
    assert as_tuple(cur_ver) > as_tuple(base_ver), (
        f"main is {base_ver}, branch is {cur_ver}: the branch version must be higher than main"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_repo_learn_validates_with_exit_zero():
    r = subprocess.run(
        ["node", "learn-app/cli.js", "validate", "--project", "."],
        capture_output=True, text=True, cwd=ROOT, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "learn OK" in r.stdout

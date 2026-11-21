# [origin ref=llm-dsl-gu1y.14 req=REQ-OPERATOR-EDU-004 c4=sdd_skills/plan_skill]
#   [intent]Audits the plan skill lesson-preparation instructions, the --dir and --docs-dir render modes of generate_diagrams.py, the plugin version bump and the repo learn/ validation against the t7 acceptance criteria[/intent]
# [/origin]

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "skills" / "docs" / "scripts" / "generate_diagrams.py"
PLAN_SKILL = ROOT / "skills" / "plan" / "SKILL.md"
PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
LEARN = ROOT / "learn"
SEED_PUML = LEARN / "backend" / "http-caching" / "diagrams" / "revalidation.puml"

PUML_OK = """@startuml fx_ok
participant "Client" as C
participant "Origin" as O
C -> O : GET /
@enduml
"""

PUML_DEPRECATED = """@startuml fx_dep
skinparam participantPadding 40
participant "Client" as C
participant "Origin" as O
C -> O : GET /
@enduml
"""

PUML_NAME_MISMATCH = """@startuml other_name
participant "Client" as C
C -> C : tick
@enduml
"""

PUML_BROKEN = """@startuml fx_bad
this is ->-> not ::: valid plantuml ((
@enduml
"""


def _plantuml_renderable() -> bool:
    if shutil.which("java") is None:
        return False
    jar = os.environ.get("PLANTUML_JAR", "")
    if jar and Path(jar).exists():
        return True
    if shutil.which("plantuml"):
        return True
    return (Path.home() / ".local" / "share" / "plantuml" / "plantuml.jar").exists()


needs_plantuml = pytest.mark.skipif(
    not _plantuml_renderable(),
    reason="java and a PlantUML jar/binary are required to render diagrams",
)


def _run_script(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def _out(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


def _write_diagram(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _plan_text() -> str:
    return PLAN_SKILL.read_text()


def test_docs_dir_missing_diagrams_folder_exits_one(tmp_path):
    docs = tmp_path / "docs" / "source"
    docs.mkdir(parents=True)

    r = _run_script(["--docs-dir", str(docs)])

    assert r.returncode == 1, _out(r)
    assert "Diagrams directory not found" in _out(r)
    assert "bootstrap_sphinx.py" in _out(r)


def test_docs_dir_empty_diagrams_folder_exits_zero(tmp_path):
    diag = tmp_path / "docs" / "source" / "architecture" / "diagrams"
    diag.mkdir(parents=True)

    r = _run_script(["--docs-dir", str(tmp_path / "docs" / "source")])

    assert r.returncode == 0, _out(r)
    assert "No .puml files found" in _out(r)


@needs_plantuml
def test_docs_dir_renders_deprecated_source_without_warning_gate(tmp_path):
    docs = tmp_path / "docs" / "source"
    diag = docs / "architecture" / "diagrams"
    src = _write_diagram(diag / "fx_dep.puml", PUML_DEPRECATED)

    r = _run_script(["--docs-dir", str(docs)])

    assert r.returncode == 0, _out(r)
    assert "PlantUML warning" not in _out(r)
    assert "1 rendered, 0 failed." in _out(r)
    svg = src.with_suffix(".svg")
    assert svg.exists(), _out(r)
    assert "deprecated" in svg.read_text().lower() or "Please" in svg.read_text(), (
        "fixture no longer triggers a PlantUML banner, so the no-gate assertion proves nothing"
    )


@needs_plantuml
def test_docs_dir_renders_clean_source_next_to_source_file(tmp_path):
    docs = tmp_path / "docs" / "source"
    diag = docs / "architecture" / "diagrams"
    src = _write_diagram(diag / "fx_ok.puml", PUML_OK)

    r = _run_script(["--docs-dir", str(docs)])

    assert r.returncode == 0, _out(r)
    assert src.with_suffix(".svg").exists()
    assert "1 rendered, 0 failed." in _out(r)


@needs_plantuml
def test_dir_renders_two_levels_deep_each_beside_its_source(tmp_path):
    top = _write_diagram(tmp_path / "lesson" / "diagrams" / "fx_ok.puml", PUML_OK)
    deep = _write_diagram(tmp_path / "lesson" / "sub" / "nested" / "diagrams" / "fx_deep.puml", PUML_OK.replace("fx_ok", "fx_deep"))

    r = _run_script(["--dir", str(tmp_path)])

    assert r.returncode == 0, _out(r)
    assert top.with_suffix(".svg").exists(), _out(r)
    assert deep.with_suffix(".svg").exists(), _out(r)
    assert "Rendering 2 diagram(s)" in _out(r)
    assert "2 rendered, 0 failed." in _out(r)


@needs_plantuml
def test_dir_ignores_non_puml_files(tmp_path):
    src = _write_diagram(tmp_path / "lesson" / "diagrams" / "fx_ok.puml", PUML_OK)
    notes = _write_diagram(tmp_path / "lesson" / "notes.md", "# not a diagram\n")
    txt = _write_diagram(tmp_path / "lesson" / "diagrams" / "readme.txt", "plain text\n")
    bak = _write_diagram(tmp_path / "lesson" / "diagrams" / "old.puml.bak", PUML_DEPRECATED)
    notes_before = notes.read_text()
    txt_before = txt.read_text()

    r = _run_script(["--dir", str(tmp_path)])

    assert r.returncode == 0, _out(r)
    assert "Rendering 1 diagram(s)" in _out(r)
    assert src.with_suffix(".svg").exists()
    assert not notes.with_suffix(".svg").exists()
    assert not txt.with_suffix(".svg").exists()
    assert not bak.with_name("old.puml.svg").exists()
    assert notes.read_text() == notes_before
    assert txt.read_text() == txt_before


@needs_plantuml
def test_dir_mixed_ok_and_deprecated_exits_one_and_names_failing_file(tmp_path):
    ok = _write_diagram(tmp_path / "lesson" / "diagrams" / "fx_ok.puml", PUML_OK)
    dep = _write_diagram(tmp_path / "lesson" / "diagrams" / "fx_dep.puml", PUML_DEPRECATED)

    r = _run_script(["--dir", str(tmp_path)])

    assert r.returncode == 1, _out(r)
    assert f"ERROR  {dep}" in r.stdout, r.stdout
    assert f"OK     {ok}" in r.stdout, r.stdout
    assert "PlantUML warning in fx_dep.svg" in r.stdout
    assert "1 rendered, 1 failed." in r.stdout


@needs_plantuml
def test_dir_name_mismatch_exits_one_and_names_expected_svg(tmp_path):
    mis = _write_diagram(tmp_path / "lesson" / "diagrams" / "fx_mis.puml", PUML_NAME_MISMATCH)

    r = _run_script(["--dir", str(tmp_path)])

    assert r.returncode == 1, _out(r)
    assert f"ERROR  {mis}" in r.stdout, r.stdout
    assert "expected fx_mis.svg next to source" in r.stdout
    assert not mis.with_suffix(".svg").exists()


@needs_plantuml
def test_dir_broken_syntax_exits_one_and_names_failing_file(tmp_path):
    bad = _write_diagram(tmp_path / "lesson" / "diagrams" / "fx_bad.puml", PUML_BROKEN)

    r = _run_script(["--dir", str(tmp_path)])

    assert r.returncode == 1, _out(r)
    assert str(bad) in _out(r), _out(r)
    assert "1 failed." in r.stdout


@needs_plantuml
def test_dir_clean_fixture_raises_no_false_positive_warning(tmp_path):
    src = _write_diagram(tmp_path / "lesson" / "diagrams" / "fx_ok.puml", PUML_OK)

    r = _run_script(["--dir", str(tmp_path)])

    assert r.returncode == 0, _out(r)
    assert "PlantUML warning" not in _out(r)
    assert "ERROR" not in _out(r)
    assert src.with_suffix(".svg").exists()
    assert "1 rendered, 0 failed." in r.stdout


@needs_plantuml
def test_dir_copy_of_seed_lesson_renders_without_warning(tmp_path):
    assert SEED_PUML.exists()
    copy = tmp_path / "learn" / "backend" / "http-caching" / "diagrams" / "revalidation.puml"
    _write_diagram(copy, SEED_PUML.read_text())

    r = _run_script(["--dir", str(tmp_path / "learn")])

    assert r.returncode == 0, _out(r)
    assert "PlantUML warning" not in _out(r)
    assert copy.with_suffix(".svg").exists()


def test_plan_exec_example_coder_line_carries_topics():
    text = _plan_text()
    assert "[job id=<BD_CODER> role=coder model=haiku|sonnet topics=iac/terraform-state]" in text


def test_plan_exec_example_tester_line_carries_depends_and_topics():
    text = _plan_text()
    assert "[job id=<BD_TESTER> role=tester model=haiku depends=<BD_CODER> topics=iac/terraform-state]" in text


def test_plan_exec_example_reviewer_line_has_no_topics():
    text = _plan_text()
    assert "[job id=<BD_REVIEWER> role=reviewer model=sonnet depends=<BD_CODER>]" in text


def test_plan_interest_deep_maps_to_all_three_levels():
    assert "| `deep` | `intro`, `working`, `deep` |" in _plan_text()


def test_plan_interest_basics_maps_to_intro_only():
    assert "| `basics` | `intro` |" in _plan_text()


def test_plan_interest_skip_maps_to_no_lessons():
    assert "| `skip` | none (generate nothing for this topic) |" in _plan_text()


def test_plan_absent_learner_json_defaults_to_basics():
    assert "If the file or the entry is absent, the interest is `basics`." in " ".join(_plan_text().split())


def test_plan_topic_entry_overrides_domain_interest():
    assert "a topic entry overrides its domain" in " ".join(_plan_text().split())


def test_plan_learn_home_defaults_to_home_sdd():
    assert 'LEARN_HOME="${SDD_LEARN_HOME:-$HOME/.sdd}"' in _plan_text()


def test_plan_render_step_uses_plugin_root_path():
    text = _plan_text()
    assert '"${CLAUDE_PLUGIN_ROOT}/skills/docs/scripts/generate_diagrams.py" --dir "$CLAUDE_PROJECT_DIR/learn"' in text


def test_plan_render_step_has_no_project_relative_script_path():
    assert "python3 skills/docs/scripts/generate_diagrams.py" not in _plan_text()


def test_plan_validate_step_uses_plugin_root_path():
    text = _plan_text()
    assert 'node "${CLAUDE_PLUGIN_ROOT}/learn-app/cli.js" validate --project "$CLAUDE_PROJECT_DIR"' in text


def test_plan_validate_runs_after_render_in_lesson_step():
    text = _plan_text()
    lesson = text[text.index("## Step 5b"):text.index("## Step 6")]
    assert lesson.index("generate_diagrams.py") < lesson.index("cli.js\" validate")


def test_plan_lesson_front_matter_requires_id_title_level_requires_sources_updated():
    text = _plan_text()
    assert "Front matter: `id: <domain>/<topic>/<NN>-<slug>`, `title`, `level`," in text
    assert "`requires:`" in text
    assert "`sources:` (at least one entry" in text
    assert "`updated:` set to today's date (`date +%F`)" in text


def test_plan_lesson_refresh_flags_stale_true_or_older_than_source_commit():
    text = _plan_text()
    assert "its front matter has `stale: true`" in text
    assert "git log -1 --format=%cs -- <path>" in text


def test_plan_lesson_step_never_blocks_the_plan_gate():
    text = _plan_text()
    assert "never asks the operator a question and never blocks the plan" in text


def test_plan_lesson_step_runs_after_confirm_gate_and_bd_creation():
    text = _plan_text()
    gate = text.index("## Step 4")
    create = text.index("## Step 5 ")
    lesson = text.index("## Step 5b")
    handoff = text.index("## Step 6")
    assert gate < create < lesson < handoff


def test_plan_lesson_failure_is_recorded_as_bd_note_and_plan_continues():
    assert "record the topic as a bd note on the plan epic and continue" in _plan_text()


def test_plan_lesson_step_generates_no_quiz_and_never_writes_docs():
    text = _plan_text()
    assert "No quiz questions are generated here." in text
    assert "Lessons never go under `docs/`." in text


def test_plan_tagging_step_uses_domain_topic_format_and_forbids_invention():
    text = _plan_text()
    assert "`<domain>/<topic>`" in text
    assert "Never invent a topic" in text


def test_plugin_version_is_2_3_0():
    data = json.loads(PLUGIN_JSON.read_text())
    assert data["version"] == "2.3.0"


def test_plugin_version_single_bump_from_main():
    try:
        base = subprocess.run(
            ["git", "show", "main:.claude-plugin/plugin.json"],
            capture_output=True, text=True, cwd=ROOT, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("main branch with plugin.json not available")
    base_ver = json.loads(base)["version"]
    cur_ver = json.loads(PLUGIN_JSON.read_text())["version"]
    if base_ver == cur_ver:
        pytest.skip("branch already merged into main; single-bump check not applicable")
    assert base_ver == "2.2.0", f"main is {base_ver}; branch must bump from 2.2.0 exactly once"
    assert cur_ver == "2.3.0", f"branch version {cur_ver}; expected a single bump to 2.3.0"


def test_every_learn_puml_has_svg_beside_it_named_after_its_stem():
    pumls = sorted(LEARN.rglob("*.puml"))
    assert len(pumls) >= 1, "expected at least one lesson diagram under learn/"
    for puml in pumls:
        svg = puml.with_suffix(".svg")
        assert svg.exists(), f"missing {svg.relative_to(ROOT)}"
        assert f"@startuml {puml.stem}" in puml.read_text(), (
            f"{puml.relative_to(ROOT)} must name its @startuml block after the file stem"
        )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_repo_learn_validates_with_exit_zero():
    r = subprocess.run(
        ["node", "learn-app/cli.js", "validate", "--project", "."],
        capture_output=True, text=True, cwd=ROOT, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "learn OK" in r.stdout


PUML_DEPRECATED_LABEL = """@startuml lbl_ok
participant "Client" as C
participant "Origin" as O
C -> O : GET / (Expires is deprecated in HTTP/1.1 docs)
@enduml
"""


@needs_plantuml
def test_dir_label_containing_word_deprecated_is_not_flagged(tmp_path):
    src = _write_diagram(tmp_path / "lesson" / "diagrams" / "lbl_ok.puml", PUML_DEPRECATED_LABEL)

    r = _run_script(["--dir", str(tmp_path)])

    assert r.returncode == 0, _out(r)
    assert src.with_suffix(".svg").exists()

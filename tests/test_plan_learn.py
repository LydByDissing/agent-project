# [origin ref=llm-dsl-gu1y.13 req=REQ-OPERATOR-EDU-004 c4=sdd_skills/plan_skill]
#   [intent]Tests that the plan phase tags exec jobs with topics=, documents the lesson-preparation step and validate command, and that generate_diagrams.py --dir renders learn/ diagrams and fails on PlantUML warning banners[/intent]
#   [inv]--dir exits non-zero whenever a rendered SVG contains a PlantUML warning text node[/inv]
# [/origin]

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dsl_parser import parse_dsl

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "skills" / "docs" / "scripts" / "generate_diagrams.py"
PLAN_SKILL = ROOT / "skills" / "plan" / "SKILL.md"
README = ROOT / "README.md"
SEED_SVG = ROOT / "learn" / "backend" / "http-caching" / "diagrams" / "revalidation.svg"

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


def _run_dir(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--dir", str(root)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_dsl_parser_keeps_topics_on_job():
    wire = (
        "[exec run=8bdf8823 feat=FEAT-OPERATOR-EDU]"
        "[job id=llm-dsl-1 role=coder model=haiku topics=iac/terraform-state]"
        "[job id=llm-dsl-2 role=tester model=haiku depends=llm-dsl-1 topics=iac/terraform-state,backend/http-caching]"
        "[/exec]"
    )
    node = parse_dsl(wire)
    jobs = node.children_by_tag("job")
    assert len(jobs) == 2
    assert jobs[0].get_attr("topics") == "iac/terraform-state"
    assert jobs[1].get_attr("topics") == "iac/terraform-state,backend/http-caching"
    assert jobs[1].get_attr("depends") == "llm-dsl-1"


@needs_plantuml
def test_generate_diagrams_dir_renders_svg_next_to_source(tmp_path):
    diag = tmp_path / "lesson" / "diagrams"
    diag.mkdir(parents=True)
    (diag / "fx_ok.puml").write_text(PUML_OK)

    r = _run_dir(tmp_path)

    assert r.returncode == 0, r.stdout + r.stderr
    svg = diag / "fx_ok.svg"
    assert svg.exists(), r.stdout
    assert "<svg" in svg.read_text()


@needs_plantuml
def test_generate_diagrams_dir_fails_on_deprecation_warning(tmp_path):
    diag = tmp_path / "lesson" / "diagrams"
    diag.mkdir(parents=True)
    (diag / "fx_dep.puml").write_text(PUML_DEPRECATED)

    r = _run_dir(tmp_path)

    assert r.returncode != 0, r.stdout + r.stderr
    assert "fx_dep.puml" in r.stdout + r.stderr
    assert "PlantUML warning" in r.stdout + r.stderr


def test_generate_diagrams_dir_missing_directory_fails(tmp_path):
    r = _run_dir(tmp_path / "does-not-exist")
    assert r.returncode != 0
    assert "Directory not found" in r.stdout


def test_generate_diagrams_dir_without_pumls_exits_zero(tmp_path):
    r = _run_dir(tmp_path)
    assert r.returncode == 0
    assert "No .puml files found" in r.stdout


def test_seed_lesson_svg_has_no_plantuml_warning_banner():
    assert SEED_SVG.exists()
    text = SEED_SVG.read_text()
    assert "Please&#160;use" not in text
    assert "Please use" not in text
    assert "deprecated" not in text.lower()


def test_plan_skill_instructs_topics_tag():
    text = PLAN_SKILL.read_text()
    assert "topics=" in text
    assert "topics=iac/terraform-state" in text
    assert "learner.json" in text
    assert "absent" in text and "basics" in text


def test_plan_skill_instructs_lesson_depth_and_skip():
    text = PLAN_SKILL.read_text()
    assert "stale: true" in text
    assert "skip" in text
    assert "intro" in text and "working" in text and "deep" in text


def test_plan_skill_instructs_render_and_validate():
    text = PLAN_SKILL.read_text()
    assert "generate_diagrams.py" in text
    assert "--dir" in text
    assert 'learn-app/cli.js" validate' in text


def test_plan_skill_exec_example_carries_topics():
    text = PLAN_SKILL.read_text()
    exec_block = text[text.rfind("[exec run=") : text.rfind("[/exec]")]
    assert "topics=" in exec_block


def test_readme_has_learn_section_with_settings():
    text = README.read_text()
    assert "## Learn while agents work" in text
    assert "node learn-app/server.js --project ." in text
    assert "SDD_LEARN=off" in text
    assert "SDD_LEARN_PORT" in text
    assert "SDD_LEARN_HOME" in text

# [origin ref=llm-dsl-gu1y.18,llm-dsl-gu1y.13 req=REQ-OPERATOR-EDU-004 c4=sdd_skills/plan_skill]
#   [intent]Tests that the plan phase tags exec jobs with topics=, documents the lesson-preparation step and validate command, and that generate_diagrams.py --dir renders learn/ diagrams and fails on PlantUML warning banners[/intent]
#   [inv]--dir exits non-zero whenever a rendered SVG contains a PlantUML warning text node[/inv]
# [/origin]

import html
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dsl_parser import parse_dsl
from tests._learn_helpers import (
    PUML_DEPRECATED,
    PUML_OK,
    ROOT,
    assert_skip_row,
    interest_row,
    load_generate_diagrams,
    needs_plantuml,
    out,
    plan_text,
    run_diagrams,
    step_section,
    write_file,
)

SEED_SVG = ROOT / "learn" / "backend" / "http-caching" / "diagrams" / "revalidation.svg"
README = ROOT / "README.md"
GD = load_generate_diagrams()


def _assert_learner_read(section: str) -> None:
    assert re.search(r"\$LEARN_HOME/learner\.json", section), "lesson step must read $LEARN_HOME/learner.json"
    assert re.search(r"\babsent\b[^.]*\binterest\b[^.]*`basics`", section, re.I), (
        "lesson step must default an absent file or entry to the `basics` interest"
    )


def _svg_with_text(tmp_path: Path, label: str) -> Path:
    return write_file(
        tmp_path / "x.svg",
        f'<svg xmlns="http://www.w3.org/2000/svg"><text x="0" y="10">{label}</text></svg>',
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
    write_file(diag / "fx_ok.puml", PUML_OK)

    r = run_diagrams(["--dir", str(tmp_path)])

    assert r.returncode == 0, out(r)
    svg = diag / "fx_ok.svg"
    assert svg.exists(), r.stdout
    assert "<svg" in svg.read_text()


@needs_plantuml
def test_generate_diagrams_dir_fails_on_deprecation_warning(tmp_path):
    diag = tmp_path / "lesson" / "diagrams"
    write_file(diag / "fx_dep.puml", PUML_DEPRECATED)

    r = run_diagrams(["--dir", str(tmp_path)])

    assert r.returncode != 0, out(r)
    assert "fx_dep.puml" in out(r)
    assert "PlantUML warning" in out(r)


def test_generate_diagrams_dir_missing_directory_fails(tmp_path):
    r = run_diagrams(["--dir", str(tmp_path / "does-not-exist")])
    assert r.returncode != 0
    assert "Directory not found" in r.stdout


def test_generate_diagrams_dir_without_pumls_exits_zero(tmp_path):
    r = run_diagrams(["--dir", str(tmp_path)])
    assert r.returncode == 0
    assert "No .puml files found" in r.stdout


@pytest.mark.parametrize(
    ("label", "flagged"),
    [
        ("Please&#160;use&#160;CSS&#160;style&#160;instead&#160;of&#160;skinparam&#160;ParticipantPadding", True),
        ("Please use CSS style instead of skinparam ParticipantPadding", True),
        ("Syntax Error? (line 3)", True),
        ("Expires is deprecated in HTTP/1.1", False),
        ("Client", False),
    ],
    ids=["banner-nbsp", "banner-plain", "syntax-error", "label-word-deprecated", "plain-label"],
)
def test_svg_warning_matcher_flags_banner_text_only(tmp_path, label, flagged):
    warns = GD.svg_warnings(_svg_with_text(tmp_path, label))
    decoded = html.unescape(label)
    if flagged:
        assert warns == [decoded], f"matcher must flag {decoded!r}, got {warns}"
    else:
        assert warns == [], f"matcher must not flag ordinary label {decoded!r}, got {warns}"


def test_seed_lesson_svg_has_no_plantuml_warning_banner():
    assert SEED_SVG.exists()
    text = SEED_SVG.read_text()
    assert "Please&#160;use" not in text
    assert "Please use" not in text
    assert "deprecated" not in text.lower()


def _assert_row(section: str, name: str) -> str:
    row = interest_row(section, name)
    assert row is not None, f"Step 5b has no interest-table row for `{name}`"
    return row


@pytest.mark.doc_contract
class TestPlanSkillDocContract:
    def test_tagging_step_requires_topics_in_domain_topic_form(self):
        sec = step_section(plan_text(), "3h")
        assert re.search(r"\btopics=", sec), "Step 3h must tell the planner to tag jobs with topics="
        assert re.search(r"<domain>/<topic>", sec), "Step 3h must give the domain/topic format"
        assert re.search(r"never\s+invent\s+a\s+topic", sec, re.I), "Step 3h must forbid inventing topics"

    def test_lesson_step_reads_learner_json_and_defaults_absent_to_basics(self):
        _assert_learner_read(step_section(plan_text(), "5b"))

    def test_lesson_step_maps_deep_to_all_levels(self):
        row = _assert_row(step_section(plan_text(), "5b"), "deep")
        assert re.findall(r"`(\w+)`", row) == ["intro", "working", "deep"]

    def test_lesson_step_maps_basics_to_intro_only(self):
        row = _assert_row(step_section(plan_text(), "5b"), "basics")
        assert re.findall(r"`(\w+)`", row) == ["intro"]

    def test_lesson_step_skip_generates_nothing(self):
        assert_skip_row(step_section(plan_text(), "5b"))

    def test_lesson_step_flags_stale_lessons_and_source_commit_check(self):
        sec = step_section(plan_text(), "5b")
        assert re.search(r"stale:\s*true", sec), "Step 5b must refresh lessons whose front matter has stale: true"
        assert re.search(r"git\s+log\s+-1\s+--format=%cs\s+--\s+<path>", sec), (
            "Step 5b must compare against the newest source commit date"
        )

    def test_lesson_step_renders_before_validating(self):
        sec = step_section(plan_text(), "5b")
        render = re.search(r"generate_diagrams\.py\"?\s+--dir\s+\"\$CLAUDE_PROJECT_DIR/learn\"", sec)
        validate = re.search(r"cli\.js\"\s+validate\b", sec)
        assert render, "Step 5b must render learn/ diagrams with generate_diagrams.py --dir"
        assert validate, "Step 5b must run cli.js validate"
        assert render.start() < validate.start(), "validate must run after the render"

    def test_exec_example_in_handoff_step_carries_topics(self):
        sec = step_section(plan_text(), "6")
        block = re.search(r"\[exec run=.*?\[/exec\]", sec, re.S)
        assert block, "Step 6 must contain an [exec] example"
        assert re.search(r"\btopics=", block.group(0)), "the [exec] example must carry topics="

    def test_negative_control_removing_skip_row_breaks_interest_contract(self):
        text = plan_text()
        mutated = "\n".join(ln for ln in text.splitlines() if not re.match(r"^\|\s*`skip`", ln))
        assert mutated != text, "positive control: the skip row must exist in the real SKILL.md"
        with pytest.raises(AssertionError, match="skip"):
            assert_skip_row(step_section(mutated, "5b"))

    def test_negative_control_learner_read_outside_lesson_step_is_rejected(self):
        text = plan_text()
        sec5b = step_section(text, "5b")
        moved = text.replace(sec5b, sec5b.replace("$LEARN_HOME/learner.json", "the learner file"))
        moved = moved.replace("### 3i. Define", "Read $LEARN_HOME/learner.json here.\n\n### 3i. Define", 1)
        assert "$LEARN_HOME/learner.json" in moved, "positive control: the phrase still exists in the document"
        with pytest.raises(AssertionError):
            _assert_learner_read(step_section(moved, "5b"))


def test_readme_has_learn_section_with_settings():
    text = README.read_text()
    assert "## Learn while agents work" in text
    assert "node learn-app/server.js --project ." in text
    assert "SDD_LEARN=off" in text
    assert "SDD_LEARN_PORT" in text
    assert "SDD_LEARN_HOME" in text

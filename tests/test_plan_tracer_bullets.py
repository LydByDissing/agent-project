# [origin ref=llm-dsl-7sg req=REQ-TRACER-BULLETS-001,REQ-TRACER-BULLETS-002,REQ-TRACER-BULLETS-003,REQ-TRACER-BULLETS-004 c4=sdd_skills/plan_skill]
#   [intent]Tests verifying tracer-bullet behaviour: type=prefactor in Task DSL, prefactor identification, observable behavior framing, exec block ordering, and file-overlap dependency analysis[/intent]
# [/origin]

import pytest
from pathlib import Path


@pytest.fixture
def rules_md_content():
    return (Path(__file__).parent.parent / "skills" / "rules" / "RULES.md").read_text()


@pytest.fixture
def skill_md_content():
    return (Path(__file__).parent.parent / "skills" / "plan" / "SKILL.md").read_text()


def _section(content: str, start_marker: str, end_marker: str) -> str:
    start = content.find(start_marker)
    end = content.find(end_marker)
    assert start != -1, f"Section start marker not found: {start_marker!r}"
    assert end != -1, f"Section end marker not found: {end_marker!r}"
    assert end > start, f"End marker appears before start marker"
    return content[start:end]


# ---------------------------------------------------------------------------
# REQ-TRACER-BULLETS-001: type=prefactor in Task DSL; prefactor identification
# ---------------------------------------------------------------------------

def test_rules_md_task_dsl_includes_prefactor_type(rules_md_content):
    assert "[task id=<id> type=code|review|test|prefactor]" in rules_md_content


def test_rules_md_task_dsl_section_documents_prefactor_purpose(rules_md_content):
    section = _section(rules_md_content,
                       "### Task (plan → worker",
                       "### Result (worker → conductor")
    assert "prefactor" in section
    assert "scaffolding" in section or "infrastructure" in section


def test_skill_md_step_3a_exists(skill_md_content):
    assert "### 3a. Identify prefactor tasks" in skill_md_content


def test_skill_md_step_3a_defines_prefactor_as_foundational_infrastructure(skill_md_content):
    section = _section(skill_md_content,
                       "### 3a. Identify prefactor tasks",
                       "### 3b.")
    assert "**Prefactor**" in section
    assert "foundational infrastructure" in section


def test_skill_md_step_3a_uses_prefactor_type(skill_md_content):
    section = _section(skill_md_content,
                       "### 3a. Identify prefactor tasks",
                       "### 3b.")
    assert "`type=prefactor`" in section


def test_skill_md_step_3a_provides_infrastructure_examples(skill_md_content):
    section = _section(skill_md_content,
                       "### 3a. Identify prefactor tasks",
                       "### 3b.")
    assert "Examples:" in section
    assert any(w in section.lower() for w in ["schema", "framework", "transport", "logging"])


def test_skill_md_step_3a_prefactors_appear_first_in_exec(skill_md_content):
    section = _section(skill_md_content,
                       "### 3a. Identify prefactor tasks",
                       "### 3b.")
    assert "first in exec block" in section


# ---------------------------------------------------------------------------
# REQ-TRACER-BULLETS-002: slice goals framed as observable behavior
# ---------------------------------------------------------------------------

def test_skill_md_step_3b_exists(skill_md_content):
    assert "### 3b. Frame each slice as observable behavior" in skill_md_content


def test_skill_md_step_3b_contrasts_bad_and_good_goal_framing(skill_md_content):
    section = _section(skill_md_content,
                       "### 3b. Frame each slice as observable behavior",
                       "### 3c.")
    assert "**Bad**:" in section
    assert "**Good**:" in section


def test_skill_md_step_3b_bad_example_is_layer_based(skill_md_content):
    section = _section(skill_md_content,
                       "### 3b. Frame each slice as observable behavior",
                       "### 3c.")
    bad_start = section.find("**Bad**:")
    good_start = section.find("**Good**:")
    bad_text = section[bad_start:good_start].lower()
    assert any(w in bad_text for w in ["implement", "model", "class", "create table", "add column"]), \
        "Bad example should describe a layer/component deliverable"


def test_skill_md_step_3b_good_example_is_behavior_based(skill_md_content):
    section = _section(skill_md_content,
                       "### 3b. Frame each slice as observable behavior",
                       "### 3c.")
    good_start = section.find("**Good**:")
    good_text = section[good_start:].lower()
    assert any(w in good_text for w in ["user can", "given", "when", "then", "returns", "receives"]), \
        "Good example should describe observable user-facing behavior"


def test_skill_md_step_3b_recommends_given_when_then(skill_md_content):
    section = _section(skill_md_content,
                       "### 3b. Frame each slice as observable behavior",
                       "### 3c.")
    assert "Given/When/Then" in section


def test_skill_md_step_3b_emphasises_testability_at_close(skill_md_content):
    section = _section(skill_md_content,
                       "### 3b. Frame each slice as observable behavior",
                       "### 3c.")
    assert "testable" in section.lower()


# ---------------------------------------------------------------------------
# REQ-TRACER-BULLETS-003: exec block ordered prefactors → happy-path → remaining
# ---------------------------------------------------------------------------

def test_skill_md_step_3f_exists(skill_md_content):
    assert "### 3f. Order the exec block" in skill_md_content


def test_skill_md_step_3f_position_1_prefactor_coders(skill_md_content):
    section = _section(skill_md_content,
                       "### 3f. Order the exec block",
                       "### 3g.")
    assert "1. Prefactor coder tasks" in section


def test_skill_md_step_3f_position_2_prefactor_testers(skill_md_content):
    section = _section(skill_md_content,
                       "### 3f. Order the exec block",
                       "### 3g.")
    assert "2. Prefactor tester tasks" in section


def test_skill_md_step_3f_position_3_happy_path_coder(skill_md_content):
    section = _section(skill_md_content,
                       "### 3f. Order the exec block",
                       "### 3g.")
    assert "3. Happy-path coder task" in section


def test_skill_md_step_3f_position_4_happy_path_tester(skill_md_content):
    section = _section(skill_md_content,
                       "### 3f. Order the exec block",
                       "### 3g.")
    assert "4. Happy-path tester task" in section


def test_skill_md_step_3f_position_5_remaining_coders(skill_md_content):
    section = _section(skill_md_content,
                       "### 3f. Order the exec block",
                       "### 3g.")
    assert "5. Remaining coder tasks" in section


def test_skill_md_step_3f_position_6_remaining_testers(skill_md_content):
    section = _section(skill_md_content,
                       "### 3f. Order the exec block",
                       "### 3g.")
    assert "6. Remaining tester tasks" in section


def test_skill_md_step_3f_position_7_reviewer_last(skill_md_content):
    section = _section(skill_md_content,
                       "### 3f. Order the exec block",
                       "### 3g.")
    assert "7. Reviewer task" in section


# ---------------------------------------------------------------------------
# REQ-TRACER-BULLETS-004: file-overlap analysis enforces independent testability
# ---------------------------------------------------------------------------

def test_skill_md_step_3e_exists(skill_md_content):
    assert "### 3e. Create tester tasks and wire file-overlap dependencies" in skill_md_content


def test_skill_md_step_3e_collects_out_paths(skill_md_content):
    section = _section(skill_md_content,
                       "### 3e. Create tester tasks and wire file-overlap dependencies",
                       "### 3f.")
    assert "Collect all `[out]` paths" in section


def test_skill_md_step_3e_infrastructural_dep_prefactor_to_slice(skill_md_content):
    section = _section(skill_md_content,
                       "### 3e. Create tester tasks and wire file-overlap dependencies",
                       "### 3f.")
    assert "Infrastructural dependency" in section or "infrastructural dependency" in section
    assert "depends=<prefactor-coder>" in section or "depends=<prefactor" in section


def test_skill_md_step_3e_shared_out_paths_require_dependency(skill_md_content):
    section = _section(skill_md_content,
                       "### 3e. Create tester tasks and wire file-overlap dependencies",
                       "### 3f.")
    assert "least one `[out]` path" in section
    assert "add `depends=" in section


def test_skill_md_step_3e_disjoint_paths_allow_parallel(skill_md_content):
    section = _section(skill_md_content,
                       "### 3e. Create tester tasks and wire file-overlap dependencies",
                       "### 3f.")
    assert "disjoint `[out]` paths" in section
    assert "can run in parallel" in section


def test_skill_md_step_3e_disjoint_paths_no_depends(skill_md_content):
    section = _section(skill_md_content,
                       "### 3e. Create tester tasks and wire file-overlap dependencies",
                       "### 3f.")
    assert "NO `depends=` between them" in section


# ---------------------------------------------------------------------------
# REQ-TRACER-BULLETS-004 (continued): Step 3d merge vs parallel strategy
# ---------------------------------------------------------------------------

def test_skill_md_step_3d_default_one_coder_per_requirement(skill_md_content):
    section = _section(skill_md_content,
                       "### 3d. Create coder tasks with vertical slices",
                       "### 3e.")
    assert "**Default: one coder task per requirement.**" in section


def test_skill_md_step_3d_merge_requires_same_component(skill_md_content):
    section = _section(skill_md_content,
                       "### 3d. Create coder tasks with vertical slices",
                       "### 3e.")
    assert "**Optional: merge requirements into a single coder task if**:" in section
    assert "same `c4_component`" in section


def test_skill_md_step_3d_merge_when_paths_overlap(skill_md_content):
    section = _section(skill_md_content,
                       "### 3d. Create coder tasks with vertical slices",
                       "### 3e.")
    assert "paths overlap" in section


def test_skill_md_step_3d_disjoint_paths_do_not_need_merging(skill_md_content):
    section = _section(skill_md_content,
                       "### 3d. Create coder tasks with vertical slices",
                       "### 3e.")
    assert "disjoint `[out]` paths do not need merging" in section

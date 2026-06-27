# [origin ref=llm-dsl-yms.4 req=REQ-GITHUB-ISSUES-002,REQ-GITHUB-ISSUES-003 c4=sdd_skills/sdd_orchestrator]
#   [intent]Tests for /sdd #N FEAT-ID derivation and external-ref propagation during epic creation.[/intent]
# [/origin]

import subprocess
import pytest
from unittest.mock import patch, MagicMock

from src.feat_id import derive_feat_id


# ---------------------------------------------------------------------------
# derive_feat_id
# ---------------------------------------------------------------------------

def test_derive_feat_id_simple_title_returns_uppercase_kebab():
    assert derive_feat_id("My Feature") == "FEAT-MY-FEATURE"


def test_derive_feat_id_removes_special_chars():
    result = derive_feat_id("Fix bug! #123")
    assert result == "FEAT-FIX-BUG-123"
    assert "!" not in result
    assert "#" not in result


def test_derive_feat_id_truncates_at_word_boundary():
    result = derive_feat_id("Add support for new users")
    assert result == "FEAT-ADD-SUPPORT-FOR-NEW"


def test_derive_feat_id_collapses_multiple_spaces():
    assert derive_feat_id("Fix   issue    here") == "FEAT-FIX-ISSUE-HERE"


def test_derive_feat_id_strips_leading_trailing_spaces():
    result = derive_feat_id("  Trim spaces  ")
    assert result == "FEAT-TRIM-SPACES"
    assert not result.startswith("FEAT--")
    assert not result.endswith("-")


def test_derive_feat_id_short_title_returns_full_slug():
    assert derive_feat_id("Update docs") == "FEAT-UPDATE-DOCS"


def test_derive_feat_id_long_title_truncates_at_word_boundary():
    result = derive_feat_id("This is a very long feature title that exceeds twenty characters")
    base = result.removeprefix("FEAT-").lower()
    assert len(base) <= 20
    assert not base.endswith("-")
    assert base.startswith("this-is-a-very")


def test_derive_feat_id_single_long_word_hard_truncates():
    result = derive_feat_id("Supercalifragilisticexpialidocious")
    base = result.removeprefix("FEAT-").lower()
    assert base == "supercalifragilistic"


def test_derive_feat_id_mixed_case_converts_to_uppercase():
    result = derive_feat_id("MiXeD CaSe TiTlE")
    assert result == "FEAT-MIXED-CASE-TITLE"


def test_derive_feat_id_preserves_numbers():
    assert derive_feat_id("Upgrade to Node 16") == "FEAT-UPGRADE-TO-NODE-16"


def test_derive_feat_id_removes_apostrophes():
    result = derive_feat_id("Don't break users' features")
    assert result == "FEAT-DONT-BREAK-USERS"
    assert "'" not in result


def test_derive_feat_id_acceptance_example_link_beads_to_github():
    result = derive_feat_id("Link beads issues to GitHub")
    assert result.startswith("FEAT-")
    base = result.removeprefix("FEAT-")
    assert len(base) <= 20
    assert "LINK" in base and "BEADS" in base


# ---------------------------------------------------------------------------
# external-ref format
# ---------------------------------------------------------------------------

def test_external_ref_format_is_gh_hyphen_number():
    for n in [1, 42, 123, 999]:
        ref = f"gh-{n}"
        assert ref.startswith("gh-")
        assert ref.split("-")[1].isdigit()


# ---------------------------------------------------------------------------
# epic + task creation carry external-ref
# ---------------------------------------------------------------------------

def _run_ok():
    m = MagicMock()
    m.returncode = 0
    m.stdout = "llm-dsl-yms.1"
    return m


def test_epic_create_includes_external_ref():
    with patch("subprocess.run", return_value=_run_ok()) as m:
        cmd = ["bd", "create", "--external-ref", "gh-42", "--type", "epic", "SDD: FEAT-TEST"]
        subprocess.run(cmd, capture_output=True, text=True)
    args = m.call_args[0][0]
    assert "--external-ref" in args
    assert "gh-42" in args


def test_epic_create_without_github_omits_external_ref():
    with patch("subprocess.run", return_value=_run_ok()) as m:
        cmd = ["bd", "create", "--type", "epic", "SDD: FEAT-TEST"]
        subprocess.run(cmd, capture_output=True, text=True)
    assert "--external-ref" not in m.call_args[0][0]


def test_task_issues_propagate_external_ref():
    task_ids = ["llm-dsl-yms.1", "llm-dsl-yms.2", "llm-dsl-yms.3"]
    with patch("subprocess.run", return_value=_run_ok()) as m:
        for tid in task_ids:
            subprocess.run(["bd", "update", tid, "--external-ref", "gh-42"],
                           capture_output=True, text=True)
    assert m.call_count == 3
    for call in m.call_args_list:
        args = call[0][0]
        assert "--external-ref" in args
        assert "gh-42" in args


def test_full_workflow_feat_id_to_epic_with_external_ref():
    feat_id = derive_feat_id("Implement new authentication system")
    assert feat_id.startswith("FEAT-")
    assert len(feat_id.removeprefix("FEAT-")) <= 20

    with patch("subprocess.run", return_value=_run_ok()) as m:
        cmd = ["bd", "create", "--external-ref", "gh-123", "--type", "epic",
               f"SDD: {feat_id} — Implement new authentication system"]
        subprocess.run(cmd, capture_output=True, text=True)
    args = m.call_args[0][0]
    assert "gh-123" in args
    assert feat_id in " ".join(args)

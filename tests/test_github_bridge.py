# [origin ref=llm-dsl-yms.2 req=REQ-GITHUB-ISSUES-001,REQ-GITHUB-ISSUES-004,REQ-GITHUB-ISSUES-005,REQ-GITHUB-ISSUES-006,REQ-GITHUB-ISSUES-007 c4=sdd_skills/github_bridge]
#   [intent]Tests for the GitHub Bridge component — all gh CLI calls are mocked.[/intent]
# [/origin]

import json
import pytest
from unittest.mock import patch, MagicMock

from src.github_bridge import (
    fetch_issue,
    update_description,
    post_comment,
    close_issue,
    move_project_card,
)


def _run(stdout="", returncode=0):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


# ---------------------------------------------------------------------------
# fetch_issue
# ---------------------------------------------------------------------------

def test_fetch_issue_contains_title_filed_and_body():
    payload = json.dumps({
        "title": "Link beads to GitHub",
        "createdAt": "2024-06-01T10:00:00Z",
        "author": {"login": "alice"},
        "body": "Feature body text.",
        "comments": [],
    })
    with patch("src.github_bridge.subprocess.run", return_value=_run(payload)):
        result = fetch_issue(3)
    assert "Link beads to GitHub" in result
    assert "2024-06-01 @alice" in result
    assert "Feature body text." in result


def test_fetch_issue_comments_include_timestamp_and_author():
    payload = json.dumps({
        "title": "T",
        "createdAt": "2024-06-01T00:00:00Z",
        "author": {"login": "alice"},
        "body": "body",
        "comments": [
            {"createdAt": "2024-06-02T08:30:00Z", "author": {"login": "bob"}, "body": "first"},
            {"createdAt": "2024-06-03T12:00:00Z", "author": {"login": "carol"}, "body": "second"},
        ],
    })
    with patch("src.github_bridge.subprocess.run", return_value=_run(payload)):
        result = fetch_issue(3)
    assert "[2024-06-02 @bob] first" in result
    assert "[2024-06-03 @carol] second" in result


def test_fetch_issue_no_comments_omits_comments_section():
    payload = json.dumps({
        "title": "T", "createdAt": "2024-06-01T00:00:00Z",
        "author": {"login": "alice"}, "body": "body", "comments": [],
    })
    with patch("src.github_bridge.subprocess.run", return_value=_run(payload)):
        result = fetch_issue(3)
    assert "Comments" not in result


def test_fetch_issue_raises_on_gh_failure():
    with patch("src.github_bridge.subprocess.run", return_value=_run("", returncode=1)):
        with pytest.raises(RuntimeError, match="gh issue view failed"):
            fetch_issue(99)


# ---------------------------------------------------------------------------
# update_description — idempotency is the key contract
# ---------------------------------------------------------------------------

def test_update_description_appends_spec_section_when_absent():
    view = _run(json.dumps({"body": "Original."}))
    edit = _run("")
    side = iter([view, edit])
    with patch("src.github_bridge.subprocess.run", side_effect=lambda *a, **kw: next(side)) as m:
        update_description(3, "FEAT-FOO\n- REQ-001")
    body = " ".join(m.call_args_list[1].args[0])
    assert "## SDD Spec" in body
    assert "Original." in body


def test_update_description_replaces_existing_spec_block():
    existing = "Intro.\n\n## SDD Spec\n\nOLD CONTENT\n"
    side = iter([_run(json.dumps({"body": existing})), _run("")])
    with patch("src.github_bridge.subprocess.run", side_effect=lambda *a, **kw: next(side)) as m:
        update_description(3, "NEW CONTENT")
    body = " ".join(m.call_args_list[1].args[0])
    assert "NEW CONTENT" in body
    assert "OLD CONTENT" not in body
    assert body.count("## SDD Spec") == 1


def test_update_description_idempotent_second_call_does_not_duplicate():
    current = ["Intro."]

    def side(*args, **kwargs):
        cmd = args[0]
        if "view" in cmd:
            return _run(json.dumps({"body": current[0]}))
        current[0] = " ".join(cmd)
        return _run("")

    with patch("src.github_bridge.subprocess.run", side_effect=side):
        update_description(3, "SPEC")
    with patch("src.github_bridge.subprocess.run", side_effect=side) as m:
        update_description(3, "SPEC")
        body = " ".join(m.call_args_list[1].args[0])
    assert body.count("## SDD Spec") == 1


def test_update_description_raises_on_edit_failure():
    side = iter([_run(json.dumps({"body": "body"})), _run("", returncode=1)])
    with patch("src.github_bridge.subprocess.run", side_effect=lambda *a, **kw: next(side)):
        with pytest.raises(RuntimeError, match="gh issue edit failed"):
            update_description(3, "section")


# ---------------------------------------------------------------------------
# post_comment
# ---------------------------------------------------------------------------

def test_post_comment_targets_correct_issue():
    with patch("src.github_bridge.subprocess.run", return_value=_run("")) as m:
        post_comment(7, "hello")
    cmd = m.call_args.args[0]
    assert "7" in cmd
    assert "hello" in cmd


def test_post_comment_raises_on_gh_failure():
    with patch("src.github_bridge.subprocess.run", return_value=_run("", returncode=1)):
        with pytest.raises(RuntimeError, match="gh issue comment failed"):
            post_comment(3, "body")


# ---------------------------------------------------------------------------
# close_issue
# ---------------------------------------------------------------------------

def test_close_issue_calls_gh_close_with_correct_number():
    with patch("src.github_bridge.subprocess.run", return_value=_run("")) as m:
        close_issue(42)
    cmd = m.call_args.args[0]
    assert "close" in cmd
    assert "42" in cmd


def test_close_issue_raises_on_gh_failure():
    with patch("src.github_bridge.subprocess.run", return_value=_run("", returncode=1)):
        with pytest.raises(RuntimeError, match="gh issue close failed"):
            close_issue(3)


# ---------------------------------------------------------------------------
# move_project_card — no-op when no board, fuzzy column matching
# ---------------------------------------------------------------------------

def test_move_project_card_noop_when_no_project_items():
    with patch("src.github_bridge.subprocess.run",
               return_value=_run(json.dumps({"projectItems": []}))) as m:
        move_project_card(3, "In Progress")
    assert m.call_count == 1


def test_move_project_card_noop_on_gh_failure():
    with patch("src.github_bridge.subprocess.run", return_value=_run("", returncode=1)) as m:
        move_project_card(3, "Done")
    assert m.call_count == 1


def test_move_project_card_noop_on_invalid_json():
    with patch("src.github_bridge.subprocess.run", return_value=_run("not-json")) as m:
        move_project_card(3, "Done")
    assert m.call_count == 1


def _project_responses(option_name="In Progress", option_id="OPT_PROG"):
    view = _run(json.dumps({
        "projectItems": [{"id": "ITEM1", "project": {"id": "PROJ1"}}]
    }))
    fields = _run(json.dumps({
        "data": {"node": {"fields": {"nodes": [
            {"id": "FLD1", "name": "Status", "options": [
                {"id": option_id, "name": option_name},
                {"id": "OPT_DONE", "name": "Done"},
            ]},
        ]}}}
    }))
    edit = _run("")
    return [view, fields, edit]


def test_move_project_card_calls_item_edit_when_project_exists():
    with patch("src.github_bridge.subprocess.run",
               side_effect=_project_responses()) as m:
        move_project_card(3, "In Progress")
    edit_cmd = m.call_args_list[2].args[0]
    assert "item-edit" in edit_cmd
    assert "OPT_PROG" in edit_cmd


def test_move_project_card_case_insensitive_column_match():
    with patch("src.github_bridge.subprocess.run",
               side_effect=_project_responses("In Progress", "OPT_PROG")) as m:
        move_project_card(3, "in progress")
    edit_cmd = m.call_args_list[2].args[0]
    assert "OPT_PROG" in edit_cmd


def test_move_project_card_underscore_variant_matches():
    with patch("src.github_bridge.subprocess.run",
               side_effect=_project_responses("In Progress", "OPT_PROG")) as m:
        move_project_card(3, "in_progress")
    edit_cmd = m.call_args_list[2].args[0]
    assert "OPT_PROG" in edit_cmd


def test_move_project_card_hyphen_variant_matches():
    with patch("src.github_bridge.subprocess.run",
               side_effect=_project_responses("In Progress", "OPT_PROG")) as m:
        move_project_card(3, "In-Progress")
    edit_cmd = m.call_args_list[2].args[0]
    assert "OPT_PROG" in edit_cmd

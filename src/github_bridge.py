# [origin ref=llm-dsl-yms.1 req=REQ-GITHUB-ISSUES-001,REQ-GITHUB-ISSUES-004,REQ-GITHUB-ISSUES-005,REQ-GITHUB-ISSUES-006,REQ-GITHUB-ISSUES-007 c4=sdd_skills/github_bridge]
#   [intent]Thin adapter wrapping gh CLI calls for GitHub issue operations used by the SDD pipeline.[/intent]
# [/origin]

from __future__ import annotations
import json
import re
import subprocess

_SPEC_HEADER = "## SDD Spec"


def _norm_col(s: str) -> str:
    return re.sub(r'[-_]', ' ', s.strip().lower())


def fetch_issue(n: int) -> str:
    r = subprocess.run(
        ["gh", "issue", "view", str(n), "--json",
         "title,createdAt,author,body,comments"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh issue view failed: {r.stderr.strip()}")
    d = json.loads(r.stdout)
    filed = (d.get("createdAt") or "")[:10]
    author = (d.get("author") or {}).get("login", "unknown")
    buf = [
        f"Title: {d.get('title', '')}",
        f"Filed: {filed} @{author}",
        "",
        (d.get("body") or "").strip(),
    ]
    comments = d.get("comments") or []
    if comments:
        buf += ["", "--- Comments ---"]
        buf += [
            f"[{(c.get('createdAt') or '')[:10]} @{(c.get('author') or {}).get('login', 'unknown')}] {(c.get('body') or '').strip()}"
            for c in comments
        ]
    return "\n".join(buf)


def update_description(n: int, section: str) -> None:
    r = subprocess.run(
        ["gh", "issue", "view", str(n), "--json", "body"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh issue view failed: {r.stderr.strip()}")
    body = json.loads(r.stdout).get("body") or ""
    new_block = f"{_SPEC_HEADER}\n\n{section}"
    if _SPEC_HEADER in body:
        body = re.sub(
            rf"{re.escape(_SPEC_HEADER)}.*?(?=\n## |\Z)",
            new_block,
            body,
            flags=re.DOTALL,
        )
    else:
        body = body.rstrip("\n") + f"\n\n{new_block}"
    r2 = subprocess.run(
        ["gh", "issue", "edit", str(n), "--body", body],
        capture_output=True, text=True,
    )
    if r2.returncode != 0:
        raise RuntimeError(f"gh issue edit failed: {r2.stderr.strip()}")


def post_comment(n: int, body: str) -> None:
    r = subprocess.run(
        ["gh", "issue", "comment", str(n), "--body", body],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh issue comment failed: {r.stderr.strip()}")


def close_issue(n: int) -> None:
    r = subprocess.run(
        ["gh", "issue", "close", str(n)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh issue close failed: {r.stderr.strip()}")


def move_project_card(n: int, column: str) -> None:
    r = subprocess.run(
        ["gh", "issue", "view", str(n), "--json", "projectItems"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return
    try:
        items = json.loads(r.stdout).get("projectItems") or []
    except json.JSONDecodeError:
        return
    if not items:
        return
    for item in items:
        pid = (item.get("project") or {}).get("id", "")
        iid = item.get("id", "")
        if not pid or not iid:
            continue
        _mv_card(pid, iid, column)


def _mv_card(pid: str, iid: str, column: str) -> None:
    q = (
        "query($id:ID!){node(id:$id){...on ProjectV2{"
        "fields(first:20){nodes{...on ProjectV2SingleSelectField{"
        "id name options{id name}}}}}}"
    )
    r = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={q}", "-F", f"id={pid}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return
    nodes = (((d.get("data") or {}).get("node") or {}).get("fields") or {}).get("nodes") or []
    for fld in nodes:
        if not fld or fld.get("name", "").lower() not in ("status", "column"):
            continue
        for opt in fld.get("options") or []:
            if _norm_col(opt.get("name") or "") == _norm_col(column):
                subprocess.run(
                    ["gh", "project", "item-edit",
                     "--project-id", pid,
                     "--id", iid,
                     "--field-id", fld["id"],
                     "--single-select-option-id", opt["id"]],
                    capture_output=True, text=True,
                )
                return

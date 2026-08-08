#!/usr/bin/env python3
"""SessionStart hook — tells the session what CodeGraph knows about this project.

The MCP server (codegraph_launch.py) is what actually indexes the code. This
hook runs alongside it and injects a short block of context so the agent knows
the graph exists, which tool answers which question, and whether the graph for
this project is warm or being built from scratch.

Reads the hook payload on stdin, writes a SessionStart hook result on stdout.
Never fails the session: any unexpected error exits 0 with no context.
"""

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codegraph_config import load_cfg, proj_root  # noqa: E402

STATE_DIR = Path.home() / ".codegraph" / "projects"

INSTALL_HINT = (
    "CodeGraph is configured for this project but not installed, so the "
    "codegraph_* tools are unavailable — fall back to Grep/Glob/Read. To enable "
    "it, the user needs to run: npm install -g @astudioplus/codegraph-mcp "
    "(then restart Claude Code)."
)

GUIDE = """CodeGraph is indexing this project — a semantic graph of its symbols,
imports, and call chains, exposed as `codegraph_*` MCP tools ({profile} profile).
Prefer it over grep for structural questions, because it answers them from
resolved edges rather than text matches:

- What is this / where is it defined  → codegraph_symbol_search, codegraph_get_symbol_info
- What calls this / what does it call → codegraph_get_callers, codegraph_get_callees
- What breaks if I change this        → codegraph_analyze_impact
- Which tests cover this              → codegraph_find_related_tests
- Context before editing a file       → codegraph_get_edit_context
- Where do I start reading            → codegraph_find_entry_points, codegraph_get_module_summary

Grep and Read stay correct for literal strings, comments, config, and prose.
{extra}"""


def idx_state(root):
    """File count for this project's persisted graph, or None when cold.

    Project namespaces are hashed, so match by looking at the paths each
    state file actually recorded rather than guessing the namespace.
    """
    root = str(Path(root).resolve())
    if not STATE_DIR.is_dir():
        return None
    for state in STATE_DIR.glob("*/index_state.json"):
        try:
            files = json.loads(state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(files, dict) or not files:
            continue
        if any(str(path).startswith(root + os.sep) for path in files):
            return len(files)
    return None


def installed():
    return bool(
        os.environ.get("CODEGRAPH_SERVER_BIN")
        or shutil.which("codegraph-mcp")
        or shutil.which("codegraph-server")
    )


def build_ctx(root):
    """The additionalContext string for this project, or None to stay silent."""
    cfg = load_cfg(root)
    if not cfg["enabled"]:
        return None
    if not installed():
        return INSTALL_HINT

    count = idx_state(root)
    if count is None:
        extra = (
            "First run on this project: the graph is being built now, so the "
            "first codegraph_* call may take a few seconds."
        )
    else:
        extra = (
            f"The graph is warm ({count} files indexed previously); changed "
            "files are re-indexed incrementally."
        )
    if cfg["graphOnly"]:
        extra += " Embeddings are off for this project — semantic search is unavailable."
    if cfg["error"]:
        extra += f" Config problem: {cfg['error']} — defaults are in use."
    return GUIDE.format(profile=cfg["profile"], extra=extra)


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}

    root = proj_root(payload.get("cwd"))
    ctx = build_ctx(root)
    if not ctx:
        return 0

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": ctx,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break a session over context injection
        print(f"codegraph session hook: {exc}", file=sys.stderr)
        sys.exit(0)

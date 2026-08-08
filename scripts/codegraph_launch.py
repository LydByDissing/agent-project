#!/usr/bin/env python3
"""MCP entry point for CodeGraph, launched by Claude Code at session start.

Declared in the plugin's `.mcp.json`, so it starts with every session and
indexes whichever project the session was opened in — the per-project part is
that the workspace, excludes, and tool profile all come from that project's
`.claude/codegraph.json` (see codegraph_config.py).

Resolution order for the server binary:

    1. $CODEGRAPH_SERVER_BIN               explicit override
    2. `codegraph-mcp` on PATH             npm install -g @astudioplus/codegraph-mcp
    3. `codegraph-server` on PATH          cargo build --release -p codegraph-server

If CodeGraph is disabled for the project, or is not installed, this serves a
stub MCP server exposing zero tools. That keeps the session clean: `/mcp` shows
codegraph connected-but-empty rather than a failed server on every start. The
SessionStart hook is what tells the user how to install it.
"""

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codegraph_config import load_cfg, proj_root, srv_args, srv_env  # noqa: E402

PROTO = "2024-11-05"


def find_bin():
    """Return (path, needs_mcp_flag) or (None, False) when nothing is installed."""
    override = os.environ.get("CODEGRAPH_SERVER_BIN")
    if override:
        # The npm wrapper injects --mcp itself; a raw Rust binary does not.
        return override, not Path(override).name.startswith("codegraph-mcp")
    wrapper = shutil.which("codegraph-mcp")
    if wrapper:
        return wrapper, False
    server = shutil.which("codegraph-server")
    if server:
        return server, True
    return None, False


def stub(reason):
    """Minimal MCP server with no tools. Keeps stdio well-formed and idles."""
    print(f"codegraph: serving no tools — {reason}", file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" not in msg:  # notification — nothing to answer
            continue
        method = msg.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": PROTO,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "codegraph (disabled)", "version": "0"},
            }
        elif method == "tools/list":
            result = {"tools": []}
        elif method in ("resources/list", "prompts/list"):
            result = {method.split("/")[0]: []}
        elif method == "ping":
            result = {}
        else:
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "error": {"code": -32601, "message": f"no such method: {method}"},
                    }
                )
                + "\n"
            )
            sys.stdout.flush()
            continue
        sys.stdout.write(
            json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}) + "\n"
        )
        sys.stdout.flush()
    return 0


def main(argv=None):
    root = proj_root()
    cfg = load_cfg(root)

    if cfg["error"]:
        print(f"codegraph: {cfg['error']} (using defaults)", file=sys.stderr, flush=True)

    if not cfg["enabled"]:
        return stub(f"disabled in {root}/.claude/codegraph.json")

    binary, needs_flag = find_bin()
    if not binary:
        return stub("codegraph is not installed (npm i -g @astudioplus/codegraph-mcp)")

    args = [binary]
    if needs_flag:
        args.append("--mcp")
    args += srv_args(cfg, root)
    args += list(argv if argv is not None else sys.argv[1:])

    # Index the project the session was opened in, whatever cwd we inherited.
    os.chdir(root)
    os.execve(binary, args, srv_env(cfg))


if __name__ == "__main__":
    sys.exit(main())

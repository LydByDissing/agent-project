#!/usr/bin/env python3
"""Per-project CodeGraph configuration for the SDD plugin.

Every project gets its own CodeGraph settings, read from
``<project>/.claude/codegraph.json``. The file is optional — when absent the
defaults below apply, so CodeGraph works on a fresh clone with no setup.

Config keys (all optional):

    enabled         bool         false disables CodeGraph for this project
    workspace       [str]        dirs to index, relative to project root (default ["."])
    exclude         [str]        dirs to skip (merged with DEF_EXCLUDE)
    maxFiles        int          indexing cap (default 5000)
    profile         str          tool surface: core | graph | memory | all (default "all")
    graphOnly       bool         skip embeddings — faster, no semantic search
    embeddingModel  str          bge-small | jina-code-v2 | granite-97m | static
    telemetry       str          "off" (default) or "on" — CodeGraph's PostHog reporting
    engine          bool         route through the shared socket engine (lower RAM)

Used by codegraph_launch.py (MCP server) and codegraph_session_start.py (hook).
"""

import json
import os
from pathlib import Path

CFG_REL = Path(".claude") / "codegraph.json"

# Directories that never carry useful graph signal. Merged with the project's
# own `exclude` list rather than replaced, so a project only adds to this.
DEF_EXCLUDE = [
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "target",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".beads",
    "_build",
]

DEF_CFG = {
    "enabled": True,
    "workspace": ["."],
    "exclude": [],
    "maxFiles": 5000,
    "profile": "all",
    "graphOnly": False,
    "embeddingModel": None,
    "telemetry": "off",
    "engine": False,
}

PROFILES = {"core", "graph", "memory", "security", "all"}


def proj_root(cwd=None):
    """Project root: CLAUDE_PROJECT_DIR when Claude Code sets it, else cwd."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()).resolve()


def load_cfg(root):
    """Read .claude/codegraph.json under `root`, merged over defaults.

    A malformed or unreadable file never breaks the session — defaults win and
    the caller is told via the returned `error` key.
    """
    cfg = dict(DEF_CFG)
    cfg["error"] = None
    path = Path(root) / CFG_REL
    if not path.is_file():
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        cfg["error"] = f"{CFG_REL}: {exc}"
        return cfg
    if not isinstance(raw, dict):
        cfg["error"] = f"{CFG_REL}: expected a JSON object"
        return cfg
    for key in DEF_CFG:
        if key in raw:
            cfg[key] = raw[key]
    if cfg["profile"] not in PROFILES:
        cfg["error"] = f"{CFG_REL}: unknown profile {cfg['profile']!r}"
        cfg["profile"] = DEF_CFG["profile"]
    return cfg


def srv_args(cfg, root):
    """Build the codegraph-server argument list for this project."""
    root = Path(root)
    args = []
    for ws in cfg["workspace"] or ["."]:
        args += ["--workspace", str((root / ws).resolve())]
    for exc in list(DEF_EXCLUDE) + list(cfg["exclude"] or []):
        args += ["--exclude", exc]
    args += ["--max-files", str(cfg["maxFiles"])]
    args += ["--profile", cfg["profile"]]
    if cfg["graphOnly"]:
        args.append("--graph-only")
    if cfg["embeddingModel"]:
        args += ["--embedding-model", cfg["embeddingModel"]]
    return args


def srv_env(cfg, base=None):
    """Environment for the server process.

    Telemetry defaults to off. An explicit CODEGRAPH_TELEMETRY in the ambient
    environment always wins, so the user can re-enable it without editing the
    plugin.
    """
    env = dict(os.environ if base is None else base)
    if "CODEGRAPH_TELEMETRY" not in env:
        env["CODEGRAPH_TELEMETRY"] = cfg["telemetry"]
    if cfg["engine"] and "CODEGRAPH_ENGINE" not in env:
        env["CODEGRAPH_ENGINE"] = "1"
    return env

"""Tests for the CodeGraph integration: config, MCP launcher, SessionStart hook.

The launcher is exercised as a real subprocess speaking MCP over stdio, so the
disabled/not-installed paths are verified to produce a well-formed server
rather than a broken pipe.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import codegraph_config as cfgmod  # noqa: E402
import codegraph_session_start as hook  # noqa: E402

LAUNCH = ROOT / "scripts" / "codegraph_launch.py"
SESSION = ROOT / "scripts" / "codegraph_session_start.py"


def write_cfg(root, cfg):
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "codegraph.json").write_text(json.dumps(cfg))


class TestConfig:
    def test_defaults_when_no_file(self, tmp_path):
        cfg = cfgmod.load_cfg(tmp_path)
        assert cfg["enabled"] is True
        assert cfg["profile"] == "all"
        assert cfg["error"] is None

    def test_file_overrides_defaults(self, tmp_path):
        write_cfg(tmp_path, {"profile": "core", "graphOnly": True, "maxFiles": 99})
        cfg = cfgmod.load_cfg(tmp_path)
        assert cfg["profile"] == "core"
        assert cfg["graphOnly"] is True
        assert cfg["maxFiles"] == 99
        assert cfg["enabled"] is True

    def test_malformed_json_falls_back_without_raising(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "codegraph.json").write_text("{not json")
        cfg = cfgmod.load_cfg(tmp_path)
        assert cfg["enabled"] is True
        assert cfg["profile"] == "all"
        assert "codegraph.json" in cfg["error"]

    def test_unknown_profile_is_rejected_and_reported(self, tmp_path):
        write_cfg(tmp_path, {"profile": "bogus"})
        cfg = cfgmod.load_cfg(tmp_path)
        assert cfg["profile"] == "all"
        assert "bogus" in cfg["error"]

    def test_args_scope_workspace_to_project_root(self, tmp_path):
        write_cfg(tmp_path, {"workspace": ["src", "tests"]})
        args = cfgmod.srv_args(cfgmod.load_cfg(tmp_path), tmp_path)
        ws = [args[i + 1] for i, a in enumerate(args) if a == "--workspace"]
        assert ws == [str(tmp_path / "src"), str(tmp_path / "tests")]

    def test_project_excludes_add_to_builtin_list(self, tmp_path):
        write_cfg(tmp_path, {"exclude": ["fixtures"]})
        args = cfgmod.srv_args(cfgmod.load_cfg(tmp_path), tmp_path)
        exc = [args[i + 1] for i, a in enumerate(args) if a == "--exclude"]
        assert "fixtures" in exc
        assert "node_modules" in exc

    def test_graph_only_and_model_flags(self, tmp_path):
        write_cfg(tmp_path, {"graphOnly": True, "embeddingModel": "static"})
        args = cfgmod.srv_args(cfgmod.load_cfg(tmp_path), tmp_path)
        assert "--graph-only" in args
        assert args[args.index("--embedding-model") + 1] == "static"

    def test_telemetry_defaults_off_but_ambient_env_wins(self, tmp_path):
        cfg = cfgmod.load_cfg(tmp_path)
        assert cfgmod.srv_env(cfg, base={})["CODEGRAPH_TELEMETRY"] == "off"
        env = cfgmod.srv_env(cfg, base={"CODEGRAPH_TELEMETRY": "on"})
        assert env["CODEGRAPH_TELEMETRY"] == "on"


class TestManifests:
    def test_plugin_manifest_wires_mcp_and_hooks(self):
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        assert (ROOT / manifest["mcpServers"]).is_file()
        assert (ROOT / manifest["hooks"]).is_file()

    def test_mcp_config_points_at_the_launcher(self):
        mcp = json.loads((ROOT / "mcp-servers.json").read_text())
        args = mcp["mcpServers"]["codegraph"]["args"]
        assert args[0].endswith("scripts/codegraph_launch.py")
        assert "${CLAUDE_PLUGIN_ROOT}" in args[0]

    def test_no_root_mcp_json_shadowing_the_plugin_config(self):
        # A root .mcp.json would also load project-scoped, where
        # ${CLAUDE_PLUGIN_ROOT} does not expand and the server fails to start.
        assert not (ROOT / ".mcp.json").exists()

    def test_hooks_json_registers_session_start(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        entry = hooks["hooks"]["SessionStart"][0]["hooks"][0]
        assert "codegraph_session_start.py" in entry["command"]
        assert "${CLAUDE_PLUGIN_ROOT}" in entry["command"]

    def test_launcher_and_hook_scripts_exist(self):
        assert LAUNCH.is_file()
        assert SESSION.is_file()


def mcp_roundtrip(root, extra_env=None):
    """Start the launcher, do an MCP handshake, return the tools/list result."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), CODEGRAPH_TELEMETRY="off")
    env.pop("CODEGRAPH_SERVER_BIN", None)
    env.update(extra_env or {})
    proc = subprocess.Popen(
        [sys.executable, str(LAUNCH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    req = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            }
        )
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
    )
    try:
        out, _ = proc.communicate(req, timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("launcher did not respond to the MCP handshake")
    msgs = {}
    for line in out.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" in msg:
            msgs[msg["id"]] = msg
    return msgs


class TestLauncher:
    def test_disabled_project_serves_a_valid_server_with_no_tools(self, tmp_path):
        write_cfg(tmp_path, {"enabled": False})
        msgs = mcp_roundtrip(tmp_path)
        assert msgs[1]["result"]["protocolVersion"]
        assert msgs[2]["result"]["tools"] == []

    def test_missing_binary_serves_no_tools_instead_of_crashing(self, tmp_path):
        msgs = mcp_roundtrip(tmp_path, extra_env={"PATH": str(tmp_path)})
        assert msgs[2]["result"]["tools"] == []

    @pytest.mark.skipif(
        not (os.environ.get("CODEGRAPH_SERVER_BIN") or shutil.which("codegraph-mcp")),
        reason="codegraph is not installed",
    )
    def test_real_server_indexes_only_the_project_and_honours_its_config(self, tmp_path):
        (tmp_path / "app.py").write_text("def greet(n):\n    return f'hi {n}'\n")
        write_cfg(tmp_path, {"profile": "core", "graphOnly": True})
        msgs = mcp_roundtrip(tmp_path)
        names = [t["name"] for t in msgs[2]["result"]["tools"]]
        assert "codegraph_symbol_search" in names
        assert len(names) == 8, f"core profile should expose 8 tools, got {names}"

    def test_binary_resolution_prefers_explicit_override(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(ROOT / "scripts"))
        import codegraph_launch as launch

        monkeypatch.setenv("CODEGRAPH_SERVER_BIN", "/opt/codegraph-server")
        path, needs_flag = launch.find_bin()
        assert path == "/opt/codegraph-server"
        assert needs_flag is True

        monkeypatch.setenv("CODEGRAPH_SERVER_BIN", "/opt/codegraph-mcp")
        _, needs_flag = launch.find_bin()
        assert needs_flag is False


def run_hook(root, payload=None):
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    proc = subprocess.run(
        [sys.executable, str(SESSION)],
        input=json.dumps(payload or {"cwd": str(root), "hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


class TestSessionHook:
    def test_disabled_project_injects_nothing(self, tmp_path):
        write_cfg(tmp_path, {"enabled": False})
        assert run_hook(tmp_path) == ""

    def test_enabled_project_injects_session_start_context(self, tmp_path):
        out = run_hook(tmp_path)
        parsed = json.loads(out)
        spec = parsed["hookSpecificOutput"]
        assert spec["hookEventName"] == "SessionStart"
        assert "codegraph" in spec["additionalContext"].lower()

    def test_context_names_tools_for_structural_questions(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hook, "installed", lambda: True)
        ctx = hook.build_ctx(tmp_path)
        for tool in (
            "codegraph_get_callers",
            "codegraph_analyze_impact",
            "codegraph_find_related_tests",
        ):
            assert tool in ctx

    def test_missing_install_yields_fallback_guidance(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hook, "installed", lambda: False)
        ctx = hook.build_ctx(tmp_path)
        assert "npm install -g @astudioplus/codegraph-mcp" in ctx
        assert "Grep" in ctx

    def test_graph_only_project_is_told_semantic_search_is_off(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hook, "installed", lambda: True)
        write_cfg(tmp_path, {"graphOnly": True})
        assert "semantic search is unavailable" in hook.build_ctx(tmp_path).lower()

    def test_cold_project_has_no_index_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hook, "STATE_DIR", tmp_path / "nowhere")
        assert hook.idx_state(tmp_path) is None

    def test_warm_index_is_matched_by_recorded_paths(self, tmp_path, monkeypatch):
        state = tmp_path / "state" / "proj-abcd"
        state.mkdir(parents=True)
        proj = tmp_path / "proj"
        proj.mkdir()
        (state / "index_state.json").write_text(
            json.dumps({str(proj / "a.py"): 1, str(proj / "b.py"): 2})
        )
        monkeypatch.setattr(hook, "STATE_DIR", tmp_path / "state")
        assert hook.idx_state(proj) == 2
        assert hook.idx_state(tmp_path / "other") is None

    def test_malformed_hook_input_does_not_fail_the_session(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(SESSION)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0

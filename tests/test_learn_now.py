# [origin ref=llm-dsl-gu1y.18,llm-dsl-gu1y.11 req=REQ-OPERATOR-EDU-010 c4=sdd_skills/conductor]
#   [intent]End-to-end tests for learn_now.py: now.json wave and job status, server start, once-per-run opener, and the never-block failure contract.[/intent]
# [/origin]

import http.server
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tests._learn_helpers import FAKE_SERVER, free_port, now_doc, run_learn_now

JOBS = json.dumps(
    [
        {"id": "llm-x.1", "title": "Coder: alpha", "topics": ["python", "sqlite"]},
        {"id": "llm-x.2", "title": "Coder: beta", "topics": "rest, auth"},
        {"id": "llm-x.3", "title": "Coder: gamma", "topics": []},
    ]
)


def _rec_lines(rec: Path) -> list[str]:
    return rec.read_text().splitlines() if rec.exists() else []


@pytest.fixture
def ctx(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    rec = tmp_path / "opened.txt"
    opener = tmp_path / "opener.sh"
    opener.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{rec}"\n')
    opener.chmod(0o755)
    fake = tmp_path / "fake_server.py"
    fake.write_text(FAKE_SERVER)
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("SDD_LEARN")}
    env.update(
        SDD_LEARN_PORT=str(port),
        SDD_LEARN_OPENER=str(opener),
        SDD_LEARN_SERVER_CMD=f"{sys.executable} {fake}",
        SDD_LEARN_WAIT_S="5",
    )
    state = {"proj": proj, "env": env, "rec": rec, "port": port, "tmp": tmp_path}
    yield state
    now = proj / ".sdd" / "now.json"
    if now.exists():
        pid = json.loads(now.read_text()).get("server_pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def _wave(ctx, run: str = "R1", wave: int = 0, jobs: str = JOBS) -> subprocess.CompletedProcess:
    return run_learn_now(
        ["wave", "--project", str(ctx["proj"]), "--run", run, "--wave", str(wave), "--jobs", jobs],
        ctx["env"],
    )


def test_wave_writes_run_wave_and_jobs_running(ctx):
    r = _wave(ctx)
    assert r.returncode == 0
    assert r.stderr == ""
    doc = now_doc(ctx["proj"])
    assert doc["run"] == "R1"
    assert doc["wave"] == 0
    assert doc["jobs"] == [
        {"id": "llm-x.1", "title": "Coder: alpha", "topics": ["python", "sqlite"], "status": "running"},
        {"id": "llm-x.2", "title": "Coder: beta", "topics": ["rest", "auth"], "status": "running"},
        {"id": "llm-x.3", "title": "Coder: gamma", "topics": [], "status": "running"},
    ]


@pytest.mark.parametrize("status", ["done", "failed"])
def test_job_status_updates_only_target_job(ctx, status):
    assert _wave(ctx).returncode == 0
    r = run_learn_now(
        ["job", "--project", str(ctx["proj"]), "--id", "llm-x.2", "--status", status],
        ctx["env"],
    )
    assert r.returncode == 0
    assert r.stderr == ""
    statuses = {j["id"]: j["status"] for j in now_doc(ctx["proj"])["jobs"]}
    assert statuses == {"llm-x.1": "running", "llm-x.2": status, "llm-x.3": "running"}
    leftovers = [p.name for p in (ctx["proj"] / ".sdd").iterdir() if p.name != "now.json"]
    assert leftovers == []


def test_wave_starts_server_that_answers_health(ctx):
    assert _wave(ctx).returncode == 0
    pid = now_doc(ctx["proj"])["server_pid"]
    assert isinstance(pid, int)
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{ctx['port']}/api/health", timeout=2) as resp:
        assert resp.status == 200


def test_wave_opens_url_once_per_run(ctx):
    assert _wave(ctx, run="R1", wave=0).returncode == 0
    assert _wave(ctx, run="R1", wave=1).returncode == 0
    url = f"http://127.0.0.1:{ctx['port']}/"
    assert _rec_lines(ctx["rec"]) == [url]
    assert now_doc(ctx["proj"])["opened_run"] == "R1"
    assert _wave(ctx, run="R2", wave=0).returncode == 0
    assert _rec_lines(ctx["rec"]) == [url, url]
    assert now_doc(ctx["proj"])["opened_run"] == "R2"


def test_wave_skips_start_when_health_already_answers(ctx):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", ctx["port"]), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        marker = ctx["tmp"] / "spawned.txt"
        ctx["env"]["SDD_LEARN_SERVER_CMD"] = f"touch {marker}"
        r = _wave(ctx)
        assert r.returncode == 0
        assert r.stderr == ""
        assert not marker.exists()
        assert "server_pid" not in now_doc(ctx["proj"])
        assert _rec_lines(ctx["rec"]) == [f"http://127.0.0.1:{ctx['port']}/"]
    finally:
        srv.shutdown()
        srv.server_close()


def test_gitignore_gets_sdd_entry_once(ctx):
    (ctx["proj"] / ".gitignore").write_text("node_modules/")
    assert _wave(ctx).returncode == 0
    assert _wave(ctx, wave=1).returncode == 0
    lines = (ctx["proj"] / ".gitignore").read_text().splitlines()
    assert lines == ["node_modules/", ".sdd/"]


def test_server_start_failure_is_one_stderr_line_exit_zero(ctx):
    ctx["env"]["SDD_LEARN_SERVER_CMD"] = "/nonexistent/learn-server-binary"
    r = _wave(ctx)
    assert r.returncode == 0
    assert len(r.stderr.strip().splitlines()) == 1
    assert "learn server failed to start" in r.stderr
    assert _rec_lines(ctx["rec"]) == []
    assert now_doc(ctx["proj"])["wave"] == 0


def test_server_never_healthy_is_one_stderr_line_and_no_open(ctx):
    ctx["env"]["SDD_LEARN_SERVER_CMD"] = "true"
    ctx["env"]["SDD_LEARN_WAIT_S"] = "0.3"
    r = _wave(ctx)
    assert r.returncode == 0
    assert len(r.stderr.strip().splitlines()) == 1
    assert "did not answer /api/health" in r.stderr
    assert _rec_lines(ctx["rec"]) == []


def test_opener_failure_is_one_stderr_line_and_retried_next_wave(ctx):
    ctx["env"]["SDD_LEARN_OPENER"] = "/nonexistent/opener"
    r = _wave(ctx)
    assert r.returncode == 0
    assert len(r.stderr.strip().splitlines()) == 1
    assert "opener" in r.stderr
    assert now_doc(ctx["proj"])["opened_run"] is None
    ctx["env"]["SDD_LEARN_OPENER"] = str(ctx["tmp"] / "opener.sh")
    assert _wave(ctx, wave=1).returncode == 0
    assert now_doc(ctx["proj"])["opened_run"] == "R1"


def test_learn_off_is_noop(ctx):
    ctx["env"]["SDD_LEARN"] = "off"
    marker = ctx["tmp"] / "spawned.txt"
    ctx["env"]["SDD_LEARN_SERVER_CMD"] = f"touch {marker}"
    r = _wave(ctx)
    assert r.returncode == 0
    assert r.stderr == ""
    r = run_learn_now(["job", "--project", str(ctx["proj"]), "--id", "llm-x.1", "--status", "done"], ctx["env"])
    assert r.returncode == 0
    assert not (ctx["proj"] / ".sdd").exists()
    assert not marker.exists()
    assert _rec_lines(ctx["rec"]) == []


def test_job_unknown_id_names_the_id_and_leaves_file_unchanged(ctx):
    assert _wave(ctx).returncode == 0
    before = (ctx["proj"] / ".sdd" / "now.json").read_text()
    r = run_learn_now(["job", "--project", str(ctx["proj"]), "--id", "llm-nope", "--status", "done"], ctx["env"])
    assert r.returncode == 0
    assert len(r.stderr.strip().splitlines()) == 1
    assert "llm-nope" in r.stderr
    assert (ctx["proj"] / ".sdd" / "now.json").read_text() == before


def test_wave_job_missing_title_names_the_key_and_writes_nothing(ctx):
    bad = json.dumps([{"id": "llm-x.9"}])
    r = _wave(ctx, jobs=bad)
    assert r.returncode == 0
    assert len(r.stderr.strip().splitlines()) == 1
    assert "'title'" in r.stderr
    assert not (ctx["proj"] / ".sdd" / "now.json").exists()

# [origin ref=llm-dsl-gu1y.18,llm-dsl-gu1y.12 req=REQ-OPERATOR-EDU-010 c4=sdd_skills/conductor]
#   [intent]Audits learn_now.py against the t6 acceptance gaps: never-break job failures, atomic now.json writes, server reuse, once-per-run open, SDD_LEARN=off, .gitignore handling, and a real node server end to end.[/intent]
# [/origin]

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from tests._learn_helpers import FAKE_SERVER, LEARN_NOW_SCRIPT, free_port, kill_pid, now_doc, run_learn_now

JOBS = json.dumps(
    [
        {"id": "llm-y.1", "title": "Coder: alpha", "topics": ["python"]},
        {"id": "llm-y.2", "title": "Coder: beta", "topics": "rest, auth"},
        {"id": "llm-y.3", "title": "Coder: gamma", "topics": []},
    ]
)


def _now_path(proj: Path) -> Path:
    return proj / ".sdd" / "now.json"


def _statuses(proj: Path) -> dict:
    return {j["id"]: j["status"] for j in now_doc(proj)["jobs"]}


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
    state = {"proj": proj, "env": env, "rec": rec, "port": port, "tmp": tmp_path, "opener": opener}
    yield state
    try:
        kill_pid(now_doc(proj).get("server_pid"))
    except (OSError, ValueError):
        pass


def _wave(ctx, run: str = "R1", wave: int = 0, jobs: str = JOBS):
    return run_learn_now(
        ["wave", "--project", str(ctx["proj"]), "--run", run, "--wave", str(wave), "--jobs", jobs],
        ctx["env"],
    )


def _job(ctx, job_id: str, status: str):
    return run_learn_now(
        ["job", "--project", str(ctx["proj"]), "--id", job_id, "--status", status],
        ctx["env"],
    )


def test_job_without_now_json_reports_one_stderr_line_and_exits_zero(ctx):
    r = _job(ctx, "llm-y.1", "done")
    assert r.returncode == 0, f"job must never break the conductor, got exit {r.returncode}: {r.stderr}"
    assert len(r.stderr.strip().splitlines()) == 1
    assert "llm-y.1" in r.stderr
    assert not _now_path(ctx["proj"]).exists(), "job must not invent a now.json it cannot fill"


def test_job_with_corrupt_now_json_names_the_file_and_exits_zero(ctx):
    (ctx["proj"] / ".sdd").mkdir()
    _now_path(ctx["proj"]).write_text("{not json")
    r = _job(ctx, "llm-y.1", "done")
    assert r.returncode == 0, f"job must never break the conductor, got exit {r.returncode}"
    assert len(r.stderr.strip().splitlines()) == 1
    assert "now.json" in r.stderr, f"stderr must name the file that failed to parse: {r.stderr!r}"
    assert "JSONDecodeError" not in r.stderr, f"stderr leaks the exception class: {r.stderr!r}"


def test_now_json_always_parses_during_rapid_job_updates(ctx):
    assert _wave(ctx).returncode == 0
    ids = ["llm-y.1", "llm-y.2", "llm-y.3"]
    seen: list[dict] = []
    bad: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                seen.append(json.loads(_now_path(ctx["proj"]).read_text()))
            except (OSError, ValueError) as e:
                bad.append(repr(e))

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        for n in range(60):
            r = _job(ctx, ids[n % 3], "done" if n % 2 else "failed")
            assert r.returncode == 0, f"job {n} failed: {r.stderr}"
    finally:
        stop.set()
        t.join(timeout=10)
    assert seen, "reader never observed now.json"
    assert bad == [], f"now.json unreadable {len(bad)} time(s) during updates, first: {bad[:1]}"
    assert _statuses(ctx["proj"]) == {"llm-y.1": "done", "llm-y.2": "failed", "llm-y.3": "done"}


def test_job_updates_leave_no_temp_files_behind(ctx):
    assert _wave(ctx).returncode == 0
    for n in range(10):
        assert _job(ctx, "llm-y.2", "done" if n % 2 else "failed").returncode == 0
    leftovers = sorted(p.name for p in (ctx["proj"] / ".sdd").iterdir() if p.name != "now.json")
    assert leftovers == [], f"temp files left in .sdd: {leftovers}"


def test_concurrent_job_updates_all_survive(ctx):
    ids = [f"llm-c.{i}" for i in range(8)]
    jobs = json.dumps([{"id": i, "title": f"t{i}", "topics": []} for i in ids])
    for rnd in range(5):
        assert _wave(ctx, run=f"R{rnd}", wave=rnd, jobs=jobs).returncode == 0
        procs = [
            subprocess.Popen(
                [sys.executable, str(LEARN_NOW_SCRIPT), "job", "--project", str(ctx["proj"]), "--id", i, "--status", "done"],
                env=ctx["env"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for i in ids
        ]
        for p in procs:
            _, err = p.communicate(timeout=60)
            assert p.returncode == 0, err
        final = _statuses(ctx["proj"])
        lost = sorted(i for i in ids if final[i] != "done")
        assert lost == [], f"round {rnd}: parallel job updates lost, still not done: {lost}"


@pytest.mark.parametrize("flag", ["off", "OFF", " off "])
def test_learn_off_variants_are_noop(ctx, flag):
    ctx["env"]["SDD_LEARN"] = flag
    marker = ctx["tmp"] / "spawned.txt"
    ctx["env"]["SDD_LEARN_SERVER_CMD"] = f"touch {marker}"
    r = _wave(ctx)
    assert r.returncode == 0
    assert r.stderr == ""
    assert not (ctx["proj"] / ".sdd").exists()
    assert not marker.exists()
    assert not (ctx["proj"] / ".gitignore").exists()
    assert not ctx["rec"].exists()


def test_gitignore_created_with_sdd_entry_when_missing(ctx):
    assert not (ctx["proj"] / ".gitignore").exists()
    assert _wave(ctx).returncode == 0
    assert (ctx["proj"] / ".gitignore").read_text() == ".sdd/\n"


def test_gitignore_with_existing_sdd_entry_is_not_changed(ctx):
    original = "node_modules/\n.sdd/\n"
    (ctx["proj"] / ".gitignore").write_text(original)
    assert _wave(ctx).returncode == 0
    assert _wave(ctx, wave=1).returncode == 0
    assert (ctx["proj"] / ".gitignore").read_text() == original


def test_gitignore_existing_content_preserved_after_repeated_waves(ctx):
    (ctx["proj"] / ".gitignore").write_text("node_modules/\n*.log\n")
    for w in range(3):
        assert _wave(ctx, wave=w).returncode == 0
    assert (ctx["proj"] / ".gitignore").read_text() == "node_modules/\n*.log\n.sdd/\n"


def test_wave_opens_url_once_across_three_waves_of_same_run(ctx):
    for w in range(3):
        assert _wave(ctx, run="R1", wave=w).returncode == 0
    url = f"http://127.0.0.1:{ctx['port']}/"
    opened = ctx["rec"].read_text().splitlines() if ctx["rec"].exists() else []
    assert opened == [url], f"expected exactly one open for run R1, got {opened}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_wave_with_default_server_cmd_serves_health_and_is_stopped(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    rec = tmp_path / "opened.txt"
    opener = tmp_path / "opener.sh"
    opener.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{rec}"\n')
    opener.chmod(0o755)
    learn_home = tmp_path / "sdd-home"
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("SDD_LEARN")}
    env.update(
        SDD_LEARN_PORT=str(port),
        SDD_LEARN_OPENER=str(opener),
        SDD_LEARN_WAIT_S="10",
        SDD_LEARN_HOME=str(learn_home),
    )
    pid = None
    try:
        started = time.monotonic()
        r = run_learn_now(["wave", "--project", str(proj), "--run", "R1", "--wave", "0", "--jobs", JOBS], env)
        elapsed = time.monotonic() - started
        assert r.returncode == 0, r.stderr
        assert r.stderr == "", f"default server start reported: {r.stderr}"
        assert elapsed < 15, f"wave blocked for {elapsed:.1f}s"
        assert (learn_home / "learner.json").exists(), "server must write learner.json under SDD_LEARN_HOME, not ~/.sdd"
        pid = now_doc(proj)["server_pid"]
        assert isinstance(pid, int)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as resp:
            assert resp.status == 200
            assert json.loads(resp.read()) == {"ok": True}
        assert rec.read_text().splitlines() == [f"http://127.0.0.1:{port}/"]
    finally:
        kill_pid(pid)
        deadline = time.monotonic() + 5
        while pid and time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.3).close()
                time.sleep(0.1)
            except OSError:
                break

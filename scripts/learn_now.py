# [origin ref=llm-dsl-gu1y.11 req=REQ-OPERATOR-EDU-010 c4=sdd_skills/conductor]
#   [intent]Publishes wave and job status to <project>/.sdd/now.json and starts and opens the Learn App once per run, without ever blocking the conductor.[/intent]
# [/origin]

import argparse
import http.client
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
SERVER_JS = PLUGIN / "learn-app" / "server.js"
SDD_DIR = ".sdd"
NOW = "now.json"
GITIGNORE_LINE = ".sdd/"
DEFAULT_PORT = "4747"
DEFAULT_WAIT_S = "5"


def _err(msg: str) -> None:
    sys.stderr.write(f"learn_now: {msg}\n")


def _off() -> bool:
    return os.environ.get("SDD_LEARN", "").strip().lower() == "off"


def _port() -> int:
    return int(os.environ.get("SDD_LEARN_PORT", DEFAULT_PORT))


def _wait_s() -> float:
    return float(os.environ.get("SDD_LEARN_WAIT_S", DEFAULT_WAIT_S))


def _now_path(proj: Path) -> Path:
    return proj / SDD_DIR / NOW


def _read_now(proj: Path) -> dict:
    p = _now_path(proj)
    return json.loads(p.read_text()) if p.exists() else {}


def _write_now(proj: Path, doc: dict) -> None:
    d = proj / SDD_DIR
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".now-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, _now_path(proj))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _ensure_gitignore(proj: Path) -> None:
    gi = proj / ".gitignore"
    text = gi.read_text() if gi.exists() else ""
    if GITIGNORE_LINE in [ln.strip() for ln in text.splitlines()]:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    gi.write_text(text + GITIGNORE_LINE + "\n")


def _norm_jobs(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError(f"--jobs must be a JSON list, got {type(raw).__name__}")
    out = []
    for j in raw:
        for k in ("id", "title"):
            if k not in j:
                raise ValueError(f"job missing '{k}': {j}")
        tp = j.get("topics", [])
        if isinstance(tp, str):
            tp = [t.strip() for t in tp.split(",") if t.strip()]
        out.append({"id": j["id"], "title": j["title"], "topics": list(tp), "status": "running"})
    return out


def _healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as r:
            return r.status == 200
    except (OSError, http.client.HTTPException):
        return False


def _await_health(port: int, wait_s: float) -> bool:
    end = time.monotonic() + wait_s
    while time.monotonic() < end:
        if _healthy(port):
            return True
        time.sleep(0.1)
    return _healthy(port)


def _server_cmd(proj: Path) -> list[str]:
    raw = os.environ.get("SDD_LEARN_SERVER_CMD")
    if raw:
        return shlex.split(raw)
    return ["node", str(SERVER_JS), "--project", str(proj)]


def _ensure_server(proj: Path, port: int) -> tuple[int | None, str | None]:
    if _healthy(port):
        return None, None
    env = dict(os.environ, SDD_LEARN_PORT=str(port))
    try:
        proc = subprocess.Popen(
            _server_cmd(proj),
            cwd=str(proj),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        return None, f"learn server failed to start: {e}"
    if not _await_health(port, _wait_s()):
        return proc.pid, f"learn server did not answer /api/health on port {port}"
    return proc.pid, None


def _open_url(url: str) -> str | None:
    raw = os.environ.get("SDD_LEARN_OPENER")
    cmd = shlex.split(raw) if raw else None
    if not cmd:
        name = "open" if sys.platform == "darwin" else "xdg-open"
        found = shutil.which(name)
        if not found:
            return f"no {name} found; open {url} manually"
        cmd = [found]
    try:
        subprocess.Popen(
            cmd + [url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        return f"opener {cmd[0]} failed: {e}; open {url} manually"
    return None


def _wave(a: argparse.Namespace) -> list[str]:
    proj = Path(a.project).resolve()
    port = _port()
    doc = _read_now(proj)
    doc.update(run=a.run, wave=a.wave, jobs=_norm_jobs(json.loads(a.jobs)))
    doc.setdefault("opened_run", None)
    url = f"http://127.0.0.1:{port}/"
    doc["url"] = url
    pid, err = _ensure_server(proj, port)
    if pid is not None:
        doc["server_pid"] = pid
    errs = [err] if err else []
    _write_now(proj, doc)
    _ensure_gitignore(proj)
    if not err and doc.get("opened_run") != a.run:
        oerr = _open_url(url)
        if oerr:
            errs.append(oerr)
        else:
            doc["opened_run"] = a.run
            _write_now(proj, doc)
    return errs


def _job(a: argparse.Namespace) -> list[str]:
    proj = Path(a.project).resolve()
    doc = _read_now(proj)
    jobs = doc.get("jobs", [])
    if not any(j["id"] == a.id for j in jobs):
        return [f"no job {a.id} in {_now_path(proj)}"]
    for j in jobs:
        if j["id"] == a.id:
            j["status"] = a.status
    _write_now(proj, doc)
    return []


def main(argv: list[str] | None = None) -> int:
    default_proj = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    ps = argparse.ArgumentParser(prog="learn_now")
    sub = ps.add_subparsers(dest="cmd", required=True)
    pw = sub.add_parser("wave")
    pw.add_argument("--project", default=default_proj)
    pw.add_argument("--run", required=True)
    pw.add_argument("--wave", required=True, type=int)
    pw.add_argument("--jobs", required=True)
    pj = sub.add_parser("job")
    pj.add_argument("--project", default=default_proj)
    pj.add_argument("--id", required=True)
    pj.add_argument("--status", required=True, choices=["done", "failed"])
    a = ps.parse_args(argv)
    if _off():
        return 0
    try:
        errs = _wave(a) if a.cmd == "wave" else _job(a)
    except Exception as e:
        errs = [f"{a.cmd} failed: {type(e).__name__}: {e}"]
    if errs:
        _err("; ".join(errs))
    return 0


if __name__ == "__main__":
    sys.exit(main())

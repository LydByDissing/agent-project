# [origin ref=llm-dsl-gu1y.18 req=REQ-OPERATOR-EDU-004,REQ-OPERATOR-EDU-010 c4=sdd_skills/plan_skill]
#   [intent]Shared fixtures and helpers for the learn and plan tests: PlantUML sources and renderability, generate_diagrams and learn_now runners, the fake learn server, and section-aware checks on plan SKILL.md.[/intent]
# [/origin]

import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DIAGRAMS_SCRIPT = ROOT / "skills" / "docs" / "scripts" / "generate_diagrams.py"
LEARN_NOW_SCRIPT = ROOT / "scripts" / "learn_now.py"
PLAN_SKILL = ROOT / "skills" / "plan" / "SKILL.md"
SVG_NS = "{http://www.w3.org/2000/svg}"
BANNER_TEXT = "Please use CSS style instead of skinparam"

PUML_OK = """@startuml fx_ok
participant "Client" as C
participant "Origin" as O
C -> O : GET /
@enduml
"""

PUML_DEPRECATED = """@startuml fx_dep
skinparam participantPadding 40
participant "Client" as C
participant "Origin" as O
C -> O : GET /
@enduml
"""

PUML_NAME_MISMATCH = """@startuml other_name
participant "Client" as C
C -> C : tick
@enduml
"""

PUML_BROKEN = """@startuml fx_bad
this is ->-> not ::: valid plantuml ((
@enduml
"""

PUML_DEPRECATED_LABEL = """@startuml lbl_ok
participant "Client" as C
participant "Origin" as O
C -> O : GET / (Expires is deprecated in HTTP/1.1 docs)
@enduml
"""

FAKE_SERVER = """
import http.server, os, threading
port = int(os.environ["SDD_LEARN_PORT"])
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/api/health" else 404)
        self.end_headers()
    def log_message(self, *a):
        pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
t = threading.Timer(60, os._exit, (0,))
t.daemon = True
t.start()
srv.serve_forever()
"""


def plantuml_renderable() -> bool:
    if shutil.which("java") is None:
        return False
    jar = os.environ.get("PLANTUML_JAR", "")
    if jar and Path(jar).exists():
        return True
    if shutil.which("plantuml"):
        return True
    return (Path.home() / ".local" / "share" / "plantuml" / "plantuml.jar").exists()


needs_plantuml = pytest.mark.skipif(
    not plantuml_renderable(),
    reason="java and a PlantUML jar/binary are required to render diagrams",
)


def out(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


def run_diagrams(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DIAGRAMS_SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def load_generate_diagrams():
    spec = importlib.util.spec_from_file_location("generate_diagrams", DIAGRAMS_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_file(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def svg_text_nodes(svg: Path) -> list[str]:
    root = ET.parse(svg).getroot()
    return [" ".join("".join(el.itertext()).replace("\xa0", " ").split()) for el in root.iter(f"{SVG_NS}text")]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_learn_now(args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LEARN_NOW_SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def now_doc(proj: Path) -> dict:
    return json.loads((proj / ".sdd" / "now.json").read_text())


def kill_pid(pid: int | None) -> None:
    if not pid:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def plan_text() -> str:
    return PLAN_SKILL.read_text()


def _heading(text: str, step: str) -> re.Match:
    m = re.search(rf"^(#{{2,3}}) (?:Step )?{re.escape(step)}(?![0-9a-z]).*$", text, re.M)
    if m is None:
        raise AssertionError(f"SKILL.md has no heading for step {step!r}")
    return m


def step_section(text: str, step: str) -> str:
    head = _heading(text, step)
    level = len(head.group(1))
    nxt = re.search(rf"^#{{1,{level}}} ", text[head.end():], re.M)
    end = head.end() + nxt.start() if nxt else len(text)
    return text[head.start():end]


def heading_pos(text: str, step: str) -> int:
    return _heading(text, step).start()


def interest_row(section: str, name: str) -> str | None:
    m = re.search(rf"^\|\s*`{name}`\s*\|(.*)$", section, re.M)
    return m.group(1) if m else None


def assert_skip_row(section: str) -> None:
    row = interest_row(section, "skip")
    assert row is not None, "lesson step has no interest-table row for `skip`"
    assert re.search(r"\bnone\b", row, re.I), f"`skip` row must generate nothing, got {row!r}"

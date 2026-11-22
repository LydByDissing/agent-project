# [origin ref=llm-dsl-2zv1.9 req=REQ-SECURITY-REVIEW-007 c4=sdd_skills/security_review]
#   [intent]Asserts the security-analyst plugin agent has read-only frontmatter and a body that states the data, injection, output and secret rules, and that its example output passes the gate validator.[/intent]
# [/origin]

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "agents" / "security-analyst.md"
GATE = ROOT / "scripts" / "security_gate.py"


def split_doc(text: str) -> tuple[dict, str]:
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    assert m, "frontmatter must be first"
    fm = {}
    for ln in m.group(1).splitlines():
        k, _, v = ln.partition(":")
        fm[k.strip()] = v.strip()
    return fm, m.group(2)


def section(body: str, title_re: str) -> str:
    parts = re.split(r"(?m)^(?=#{2,3} )", body)
    for p in parts:
        if re.match(rf"#{{2,3}} .*{title_re}", p, re.I):
            return p
    return ""


def has(text: str, *pats: str) -> bool:
    text = re.sub(r"\s+", " ", text)
    return all(re.search(p, text, re.I | re.S) for p in pats)


FM, BODY = split_doc(AGENT.read_text(encoding="utf-8"))


def test_frontmatter():
    assert FM["name"] == "security-analyst"
    assert FM["model"] == "opus"
    assert {t.strip() for t in FM["tools"].split(",")} == {"Read", "Grep", "Glob"}
    assert FM["description"]


def test_origin_header_after_frontmatter():
    assert BODY.lstrip().startswith("<!-- [origin")


def test_data_delimiters():
    assert has(BODY, r"<<<DATA", r"DATA>>>")
    inp = section(BODY, "input")
    for k in ("spec", "adr", "threat-model", "diff", "code"):
        assert k in inp


def test_injection_rule():
    s = section(BODY, "instructions|data")
    assert has(s, r"never follow|do not follow|not follow", r"possible-injection", r"med")


def test_json_only_output():
    s = section(BODY, "output")
    assert has(s, r"only a json array")
    for f in ("id", "severity", "stride", "element", "anchor", "threat", "mitigation", "links"):
        assert re.search(rf"`{f}`", s)


def test_length_limits():
    assert has(BODY, r"threat.{0,40}400", r"mitigation.{0,40}400", r"120")
    assert has(BODY, r"«…»")


def test_no_secret_value():
    assert has(section(BODY, "rules"), r"never print a secret value", r"file:line")


def test_no_exploit_steps():
    assert has(section(BODY, "rules"), r"no step-by-step exploitation")


def test_methods():
    d = re.sub(r"\s+", " ", section(BODY, "STRIDE"))
    for w in ("Spoofing", "Tampering", "Repudiation", "Information disclosure", "Denial of service", "Elevation of privilege"):
        assert w in d
    p = section(BODY, "OWASP")
    for w in ("input handling", "authentication", "injection", "secrets", "path", "SSRF", "CSRF", "deserialisation", "logging"):
        assert re.search(w, p, re.I), w


def test_decided_rule():
    assert has(BODY, r"decided", r"do not re-raise")


def test_no_write_tool_request():
    assert has(BODY, r"never ask for any")


def test_negative_control():
    mutated = BODY.replace("Output ONLY a JSON array", "Output text")
    assert not has(section(mutated, "output"), r"only a json array")
    assert not has(BODY.replace("Never print a secret value", "x"), r"never print a secret value")
    with pytest.raises(AssertionError):
        split_doc("no frontmatter")


def example_findings() -> list:
    blk = re.search(r"```json\n(.*?)\n```", BODY, re.S)
    assert blk
    return json.loads(blk.group(1))


def test_example_passes_validate(tmp_path):
    fs = example_findings()
    for f in fs:
        assert len(f["threat"]) <= 400 and len(f["mitigation"]) <= 400
    p = tmp_path / "f.json"
    p.write_text(json.dumps(fs))
    r = subprocess.run([sys.executable, str(GATE), "validate", "--feature", "FEAT-SECURITY-REVIEW", "--findings", str(p)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr


def test_validate_rejects_mutated_example(tmp_path):
    fs = example_findings()
    del fs[0]["anchor"]
    p = tmp_path / "f.json"
    p.write_text(json.dumps(fs))
    r = subprocess.run([sys.executable, str(GATE), "validate", "--feature", "FEAT-SECURITY-REVIEW", "--findings", str(p)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode != 0

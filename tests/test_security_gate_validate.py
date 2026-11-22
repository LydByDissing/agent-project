# [origin ref=llm-dsl-2zv1.1 req=REQ-SECURITY-REVIEW-013,REQ-SECURITY-REVIEW-003 c4=sdd_skills/security_review]
#   [intent]Tests security_gate.py validate and security_gate_lib parsing against tmp-dir fixtures and the real repo docs.[/intent]
# [/origin]

import re
import json
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "security_gate.py"
sys.path.insert(0, str(ROOT / "scripts"))
import security_gate_lib as lib

FEAT = "FEAT-X"
SPEC = """.. feat:: X
   :id: FEAT-X

.. req:: One
   :id: REQ-X-001
   :links: FEAT-X
   :acceptance: multi
       line

   body

.. req:: Foreign
   :id: REQ-OTHER-001
   :links: FEAT-OTHER
"""
ARCH = """Comps
=====

Sec Thing
~~~~~~~~~

text

Other Thing (``other_id``)
~~~~~~~~~~~~~~~~~~~~~~~~~~

x

.. list-table::

   * - Name
     - Type
   * - Big Box
     - App
"""
THREAT = """.. threat:: T one
   :id: THREAT-MY-BOX-001
   :status: open
   :links: REQ-X-001

   body

.. threat:: T foreign
   :id: THREAT-MY-BOX-002
   :links: REQ-OTHER-001
"""
REVIEWS = """Reviews

.. list-table::

   * - Run
     - Stage
   * - 87708f1a
     - design
     - 1
     - a..b
     - 2 (A-01..02)
     - done
   * - deadbeef
     - post
     - 1
     - b..c
     - 0
     - clean
"""


def good() -> dict:
    return {"id": "F1", "severity": "high", "stride": "T/E", "element": "sec_thing", "anchor": "a.py:1",
            "threat": "t", "mitigation": "m", "links": ["REQ-X-001", "THREAT-MY-BOX-001"]}


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    d = tmp_path / "docs"
    for rel, txt in {"specs/f.rst": SPEC, "architecture/components/c.rst": ARCH,
                     "security/threat-model/my-box.rst": THREAT, "security/reviews.rst": REVIEWS,
                     "security/accepted-risks.rst": ".. risk:: R\n   :id: RISK-001\n"}.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt)
    return d


def run(docs: Path, tmp: Path, findings=None, feat: str = FEAT):
    cmd = [sys.executable, str(SCRIPT), "validate", "--feature", feat, "--docs", str(docs)]
    if findings is not None:
        fp = tmp / "f.json"
        fp.write_text(json.dumps(findings))
        cmd += ["--findings", str(fp)]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_parse_counts_and_multiline_opts(docs):
    d = lib.load(docs)
    assert [len(d["threats"]), len(d["risks"]), len(d["reviews"])] == [2, 1, 2]
    req = [n for n in d["needs"] if n["opts"].get("id") == "REQ-X-001"][0]
    assert req["opts"]["acceptance"] == "multi line"
    assert lib.feat_reqs(d, FEAT) == {"REQ-X-001"}
    assert {"sec_thing", "other_id", "big_box"} <= d["c4"]


def test_validate_ok_no_findings(docs, tmp_path):
    r = run(docs, tmp_path)
    assert r.returncode == 0, r.stderr
    assert "2 threats, 1 risks, 2 review records" in r.stdout


def test_validate_good_finding_passes(docs, tmp_path):
    assert run(docs, tmp_path, [good()]).returncode == 0
    assert run(docs, tmp_path, {"findings": [good()]}).returncode == 0


@pytest.mark.parametrize("field,val,msg", [
    ("severity", "critical", "severity 'critical'"),
    ("stride", "X", "stride 'X'"),
    ("stride", "T//E", "stride 'T//E'"),
    ("stride", "T/T", "stride 'T/T'"),
    ("stride", "t", "stride 't'"),
    ("element", "made_up", "C4 element 'made_up'"),
    ("links", ["REQ-X-999"], "REQ-X-999 does not resolve"),
    ("links", ["REQ-OTHER-001"], "REQ-OTHER-001 does not belong to feature FEAT-X"),
    ("links", ["THREAT-MY-BOX-009"], "THREAT-MY-BOX-009 does not resolve"),
    ("links", ["THREAT-MY-BOX-002"], "THREAT-MY-BOX-002 does not belong to feature FEAT-X"),
    ("links", ["BOGUS-1"], "neither a REQ nor a THREAT"),
])
def test_validate_rejects_rule(docs, tmp_path, field, val, msg):
    f = good()
    f[field] = val
    r = run(docs, tmp_path, [f])
    assert r.returncode != 0
    assert "finding F1:" in r.stderr and msg in r.stderr


def test_each_bad_finding_named(docs, tmp_path):
    a, b = good(), good()
    a["id"], a["severity"] = "A", "bad"
    b["id"], b["element"] = "B", "nope"
    r = run(docs, tmp_path, [a, b])
    assert r.returncode == 1
    assert "finding A:" in r.stderr and "finding B:" in r.stderr


def test_missing_field_and_non_object_and_duplicate(docs, tmp_path):
    f = good()
    del f["anchor"]
    r = run(docs, tmp_path, [f, good(), good(), "str"])
    assert r.returncode == 1
    assert "finding F1: missing field anchor" in r.stderr
    assert "finding F1: duplicate id" in r.stderr
    assert "finding #3: not an object" in r.stderr


def test_links_as_string_and_empty_element(docs, tmp_path):
    f = good()
    f["links"] = "REQ-X-001, REQ-X-404"
    f["element"] = ""
    r = run(docs, tmp_path, [f])
    assert "REQ-X-404 does not resolve" in r.stderr and "is not a C4 id" in r.stderr


def test_unknown_feature_and_bad_findings_file(docs, tmp_path):
    assert "feature FEAT-NOPE not found" in run(docs, tmp_path, feat="FEAT-NOPE").stderr
    (tmp_path / "bad.json").write_text("{not json")
    r = subprocess.run([sys.executable, str(SCRIPT), "validate", "--feature", FEAT, "--docs", str(docs),
                        "--findings", str(tmp_path / "bad.json")], capture_output=True, text=True)
    assert r.returncode == 1 and "findings unreadable" in r.stderr


def test_threat_id_format_and_duplicates(docs, tmp_path):
    p = docs / "security/threat-model/my-box.rst"
    p.write_text(THREAT + "\n.. threat:: bad\n   :id: THREAT-WRONG-001\n\n.. threat:: dup\n   :id: THREAT-MY-BOX-001\n")
    r = run(docs, tmp_path)
    assert r.returncode == 1
    assert "THREAT-WRONG-001 must be THREAT-MY-BOX-NNN" in r.stderr
    assert "duplicate id THREAT-MY-BOX-001" in r.stderr


def test_real_repo_docs():
    r = subprocess.run([sys.executable, str(SCRIPT), "validate", "--feature", "FEAT-SECURITY-REVIEW"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    t, k, n = _repo_record_counts()
    assert f"{t} threats, {k} risks, {n} review records" in r.stdout
    d = lib.load(ROOT / "docs/source")
    assert {"security_review", "sdd_orchestrator", "sdd_skills"} <= d["c4"]
    assert len(lib.feat_reqs(d, "FEAT-SECURITY-REVIEW")) == 13


def test_real_repo_finding_rules_fire():
    d = lib.load(ROOT / "docs/source")
    f = good() | {"element": "security_review", "links": ["REQ-SECURITY-REVIEW-013", "THREAT-SDD-SKILLS-001"]}
    assert lib.validate_findings([f], d, "FEAT-SECURITY-REVIEW") == []
    f["links"] = ["REQ-OPERATOR-EDU-001"]
    assert len(lib.validate_findings([f], d, "FEAT-SECURITY-REVIEW")) == 1

def _repo_record_counts():
    sec = Path(__file__).resolve().parent.parent / "docs/source/security"
    threats = sum(len(re.findall(r"^\.\. threat::", f.read_text(), re.M)) for f in (sec / "threat-model").glob("*.rst"))
    risks = len(re.findall(r"^\.\. risk::", (sec / "accepted-risks.rst").read_text(), re.M))
    rows = len(re.findall(r"^   \* - [0-9a-f]{8}\s*$", (sec / "reviews.rst").read_text(), re.M))
    return threats, risks, rows


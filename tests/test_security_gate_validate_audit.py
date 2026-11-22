# [origin ref=llm-dsl-2zv1.2 req=REQ-SECURITY-REVIEW-013,REQ-SECURITY-REVIEW-003 c4=sdd_skills/security_review]
#   [intent]Audits security_gate.py validate with failing and passing controls for every finding rule, record rule, CLI exit code and findings file shape.[/intent]
# [/origin]

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "security_gate.py"

FEAT = "FEAT-A"
SPEC = """.. feat:: A
   :id: FEAT-A

.. feat:: B
   :id: FEAT-B

.. req:: A one
   :id: REQ-A-001
   :links: FEAT-A

.. req:: A two
   :id: REQ-A-002
   :links: FEAT-A

.. req:: B one
   :id: REQ-B-001
   :links: FEAT-B
"""
ARCH = """Comps
=====

Alpha Part
~~~~~~~~~~

text

Beta Part (``beta_id``)
~~~~~~~~~~~~~~~~~~~~~~~
"""
THREAT_A = """.. threat:: mixed
   :id: THREAT-MY-BOX-001
   :links: REQ-B-001, REQ-A-002

.. threat:: only a
   :id: THREAT-MY-BOX-002
   :links: REQ-A-001

.. threat:: only b
   :id: THREAT-MY-BOX-003
   :links: REQ-B-001
"""
REVIEWS = """Reviews

.. list-table::

   * - Run
     - Stage
   * - 87708f1a
     - design
     - 1
     - a..b
     - 0
     - done
"""
RISK = ".. risk:: R\n   :id: RISK-001\n"


def finding(**over) -> dict:
    base = {"id": "F1", "severity": "high", "stride": "T/E", "element": "alpha_part", "anchor": "a.py:1",
            "threat": "t", "mitigation": "m", "links": ["REQ-A-001", "THREAT-MY-BOX-002"]}
    return base | over


def put(root: Path, files: dict) -> None:
    for rel, txt in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt)


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    d = tmp_path / "docs"
    put(d, {"specs/f.rst": SPEC, "architecture/c.rst": ARCH, "security/threat-model/my-box.rst": THREAT_A,
            "security/reviews.rst": REVIEWS, "security/accepted-risks.rst": RISK})
    return d


def cli(docs: Path, *extra: str, feat: str = FEAT):
    cmd = [sys.executable, str(SCRIPT), "validate", "--feature", feat, "--docs", str(docs), *extra]
    return subprocess.run(cmd, capture_output=True, text=True)


def validate(docs: Path, findings, feat: str = FEAT):
    fp = docs.parent / "findings.json"
    fp.write_text(json.dumps(findings))
    return cli(docs, "--findings", str(fp), feat=feat)


def test_real_repo_reports_exact_counts_and_exits_zero():
    r = subprocess.run([sys.executable, str(SCRIPT), "validate", "--feature", "FEAT-SECURITY-REVIEW"],
                       capture_output=True, text=True, cwd=ROOT)

    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "feature FEAT-SECURITY-REVIEW: 21 threats, 0 risks, 4 review records"
    assert r.stderr == ""


def test_real_repo_unknown_feature_fails():
    r = subprocess.run([sys.executable, str(SCRIPT), "validate", "--feature", "FEAT-NO-SUCH"],
                       capture_output=True, text=True, cwd=ROOT)

    assert r.returncode == 1
    assert "feature FEAT-NO-SUCH not found" in r.stderr


def test_fixture_without_findings_reports_counts_exit_zero(docs):
    r = cli(docs)

    assert r.returncode == 0, r.stderr
    assert "3 threats, 1 risks, 1 review records" in r.stdout


@pytest.mark.parametrize("sev", ["crit", "high", "med", "low"])
def test_severity_accepts_each_allowed_value(docs, sev):
    r = validate(docs, [finding(severity=sev)])

    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("sev", ["critical", "High", "HIGH", "medium", "", None, 3, ["high"]])
def test_severity_rejects_invalid_value(docs, sev):
    r = validate(docs, [finding(severity=sev)])

    assert r.returncode == 1
    assert "finding F1: severity" in r.stderr
    assert "Traceback" not in r.stderr


@pytest.mark.parametrize("st", ["S", "T", "R", "I", "D", "E", "T/E", "S/T/R/I/D/E", "E/S"])
def test_stride_accepts_valid_letters_and_slash_combinations(docs, st):
    r = validate(docs, [finding(stride=st)])

    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("st", ["TT", "X", "T/", "/T", "T//E", "T/T", "t", "t/e", "TE", "T,E", "T E", "", "S/X", None, 5, ["T"]])
def test_stride_rejects_invalid_value(docs, st):
    r = validate(docs, [finding(stride=st)])

    assert r.returncode == 1
    assert "finding F1: stride" in r.stderr
    assert "Traceback" not in r.stderr


@pytest.mark.parametrize("field", ["id", "severity", "stride", "element", "anchor", "threat", "mitigation", "links"])
def test_missing_field_is_named(docs, field):
    f = finding()
    del f[field]

    r = validate(docs, [f])

    assert r.returncode == 1
    assert f"missing field {field}" in r.stderr
    assert "Traceback" not in r.stderr


def test_duplicate_finding_id_is_reported(docs):
    r = validate(docs, [finding(), finding()])

    assert r.returncode == 1
    assert "finding F1: duplicate id" in r.stderr


def test_distinct_finding_ids_pass(docs):
    r = validate(docs, [finding(id="F1"), finding(id="F2")])

    assert r.returncode == 0, r.stderr


def test_element_known_container_id_from_headings_passes(docs):
    assert validate(docs, [finding(element="alpha_part")]).returncode == 0
    assert validate(docs, [finding(element="beta_id")]).returncode == 0


def test_element_unknown_id_is_rejected(docs):
    r = validate(docs, [finding(element="gamma")])

    assert r.returncode == 1
    assert "finding F1: C4 element 'gamma' not found" in r.stderr


def test_element_with_one_unknown_among_known_is_rejected(docs):
    r = validate(docs, [finding(element="alpha_part, gamma")])

    assert r.returncode == 1
    assert "C4 element 'gamma'" in r.stderr
    assert "C4 element 'alpha_part'" not in r.stderr


@pytest.mark.parametrize("el", ["", "   ", None, 7, ["alpha_part"]])
def test_element_empty_or_non_string_is_rejected(docs, el):
    r = validate(docs, [finding(element=el)])

    assert r.returncode == 1
    assert "finding F1: element" in r.stderr
    assert "Traceback" not in r.stderr


def test_req_link_in_feature_passes(docs):
    r = validate(docs, [finding(links=["REQ-A-001", "REQ-A-002"])])

    assert r.returncode == 0, r.stderr


def test_req_link_that_does_not_resolve_is_rejected(docs):
    r = validate(docs, [finding(links=["REQ-A-999"])])

    assert r.returncode == 1
    assert "link REQ-A-999 does not resolve to a requirement" in r.stderr


def test_req_link_of_another_feature_is_rejected_with_foreign_message(docs):
    r = validate(docs, [finding(links=["REQ-B-001"])])

    assert r.returncode == 1
    assert "link REQ-B-001 does not belong to feature FEAT-A" in r.stderr
    assert "does not resolve" not in r.stderr


def test_req_link_passes_when_feature_under_review_is_the_other_one(docs):
    r = validate(docs, [finding(links=["REQ-B-001"])], feat="FEAT-B")

    assert r.returncode == 0, r.stderr


def test_threat_link_to_threat_of_feature_passes(docs):
    r = validate(docs, [finding(links=["THREAT-MY-BOX-002"])])

    assert r.returncode == 0, r.stderr


def test_threat_link_linking_both_features_passes_for_either(docs):
    assert validate(docs, [finding(links=["THREAT-MY-BOX-001"])]).returncode == 0
    assert validate(docs, [finding(links=["THREAT-MY-BOX-001"])], feat="FEAT-B").returncode == 0


def test_threat_link_that_does_not_resolve_is_rejected(docs):
    r = validate(docs, [finding(links=["THREAT-MY-BOX-099"])])

    assert r.returncode == 1
    assert "link THREAT-MY-BOX-099 does not resolve to a threat" in r.stderr


def test_threat_link_whose_threat_only_links_other_feature_is_rejected(docs):
    r = validate(docs, [finding(links=["THREAT-MY-BOX-003"])])

    assert r.returncode == 1
    assert "link THREAT-MY-BOX-003 does not belong to feature FEAT-A" in r.stderr


def test_threat_without_links_is_foreign_to_every_feature(docs):
    put(docs, {"security/threat-model/my-box.rst": THREAT_A + "\n.. threat:: nolink\n   :id: THREAT-MY-BOX-004\n"})

    r = validate(docs, [finding(links=["THREAT-MY-BOX-004"])])

    assert r.returncode == 1
    assert "THREAT-MY-BOX-004 does not belong to feature FEAT-A" in r.stderr


def test_link_with_unknown_prefix_is_rejected(docs):
    r = validate(docs, [finding(links=["ADR-001"])])

    assert r.returncode == 1
    assert "neither a REQ nor a THREAT id" in r.stderr


@pytest.mark.parametrize("links", [None, 5, {"a": 1}, [1, None]])
def test_links_of_wrong_type_are_rejected_without_traceback(docs, links):
    r = validate(docs, [finding(links=links)])

    assert r.returncode == 1
    assert "finding F1:" in r.stderr
    assert "Traceback" not in r.stderr


def test_links_given_as_comma_string_are_each_checked(docs):
    r = validate(docs, [finding(links="REQ-A-001, REQ-A-999")])

    assert r.returncode == 1
    assert "REQ-A-999 does not resolve" in r.stderr
    assert "REQ-A-001 " not in r.stderr


def test_every_problem_is_printed_not_only_the_first(docs):
    bad = finding(id="A", severity="bad", stride="X", element="nope", links=["REQ-B-001", "THREAT-MY-BOX-099"])
    del bad["anchor"]
    other = finding(id="B", severity="bad")

    r = validate(docs, [bad, other])

    errs = [ln for ln in r.stderr.splitlines() if ln.startswith("ERROR")]
    assert r.returncode == 1
    assert len(errs) == 7, r.stderr
    assert sum("finding A:" in e for e in errs) == 6
    assert sum("finding B:" in e for e in errs) == 1


def test_non_object_finding_is_reported_by_index(docs):
    r = validate(docs, [finding(), "text", None, 4])

    assert r.returncode == 1
    for idx in (1, 2, 3):
        assert f"finding #{idx}: not an object" in r.stderr


def test_findings_accepted_as_bare_list(docs):
    assert validate(docs, [finding()]).returncode == 0


def test_findings_accepted_in_findings_object(docs):
    assert validate(docs, {"findings": [finding()]}).returncode == 0


def test_findings_object_bad_finding_is_still_validated(docs):
    r = validate(docs, {"findings": [finding(severity="bad")]})

    assert r.returncode == 1
    assert "finding F1: severity" in r.stderr


def test_empty_findings_list_passes(docs):
    assert validate(docs, []).returncode == 0


@pytest.mark.parametrize("payload", [{"other": []}, {"findings": "x"}, {"findings": {"a": 1}}, 5, "str", None])
def test_findings_wrong_shape_gives_clear_error(docs, payload):
    r = validate(docs, payload)

    assert r.returncode == 1
    assert "findings unreadable" in r.stderr
    assert "Traceback" not in r.stderr


@pytest.mark.parametrize("text", ["{not json", "", "[1,", "\x00"])
def test_malformed_json_gives_clear_error_not_traceback(docs, text):
    fp = docs.parent / "bad.json"
    fp.write_text(text)

    r = cli(docs, "--findings", str(fp))

    assert r.returncode == 1
    assert "findings unreadable" in r.stderr
    assert "Traceback" not in r.stderr


def test_findings_file_with_invalid_utf8_gives_clear_error(docs):
    fp = docs.parent / "bin.json"
    fp.write_bytes(b"\xff\xfe\x00bad")

    r = cli(docs, "--findings", str(fp))

    assert r.returncode == 1
    assert "findings unreadable" in r.stderr
    assert "Traceback" not in r.stderr


def test_missing_findings_file_gives_clear_error(docs):
    r = cli(docs, "--findings", str(docs.parent / "absent.json"))

    assert r.returncode == 1
    assert "findings unreadable" in r.stderr
    assert "Traceback" not in r.stderr


def test_unreadable_findings_still_reports_record_problems(docs):
    put(docs, {"security/threat-model/my-box.rst": THREAT_A + "\n.. threat:: dup\n   :id: THREAT-MY-BOX-001\n"})
    fp = docs.parent / "bad.json"
    fp.write_text("{")

    r = cli(docs, "--findings", str(fp))

    assert "findings unreadable" in r.stderr
    assert "duplicate id THREAT-MY-BOX-001" in r.stderr


def test_unknown_feature_exits_nonzero_and_names_it(docs):
    r = cli(docs, feat="FEAT-NOPE")

    assert r.returncode == 1
    assert "feature FEAT-NOPE not found" in r.stderr


def test_missing_feature_argument_exits_usage_error(docs):
    r = subprocess.run([sys.executable, str(SCRIPT), "validate", "--docs", str(docs)], capture_output=True, text=True)

    assert r.returncode == 2
    assert "--feature" in r.stderr


def test_unknown_subcommand_exits_usage_error():
    r = subprocess.run([sys.executable, str(SCRIPT), "bogus"], capture_output=True, text=True)

    assert r.returncode == 2


def test_threat_id_container_mismatch_with_file_name_is_rejected(docs):
    put(docs, {"security/threat-model/my-box.rst": ".. threat:: x\n   :id: THREAT-OTHER-BOX-001\n   :links: REQ-A-001\n"})

    r = cli(docs)

    assert r.returncode == 1
    assert "THREAT-OTHER-BOX-001 must be THREAT-MY-BOX-NNN" in r.stderr


def test_threat_container_derived_from_underscored_file_name(docs):
    put(docs, {"security/threat-model/my_box.rst": ".. threat:: x\n   :id: THREAT-MY-BOX-010\n   :links: REQ-A-001\n"})

    assert cli(docs).returncode == 0
    put(docs, {"security/threat-model/my_box.rst": ".. threat:: x\n   :id: THREAT-MY_BOX-010\n   :links: REQ-A-001\n"})
    assert cli(docs).returncode == 1


@pytest.mark.parametrize("bad", ["THREAT-MY-BOX-01", "THREAT-MY-BOX-0001", "THREAT-my-box-001", "threat-my-box-001", "THREAT-MY-BOX-ABC"])
def test_threat_id_number_and_case_format_is_enforced(docs, bad):
    put(docs, {"security/threat-model/my-box.rst": f".. threat:: x\n   :id: {bad}\n   :links: REQ-A-001\n"})

    r = cli(docs)

    assert r.returncode == 1
    assert f"threat id {bad} must be" in r.stderr


def test_threat_without_id_is_reported(docs):
    put(docs, {"security/threat-model/my-box.rst": THREAT_A + "\n.. threat:: noid\n   :status: open\n"})

    r = cli(docs)

    assert r.returncode == 1
    assert "threat has no :id:" in r.stderr


def test_duplicate_threat_id_across_files_is_reported(docs):
    put(docs, {"security/threat-model/other.rst": ".. threat:: x\n   :id: THREAT-MY-BOX-001\n"})

    r = cli(docs)

    assert r.returncode == 1
    assert "duplicate id THREAT-MY-BOX-001" in r.stderr


def test_duplicate_risk_id_is_reported(docs):
    put(docs, {"security/accepted-risks.rst": RISK + "\n" + RISK})

    r = cli(docs)

    assert r.returncode == 1
    assert "duplicate id RISK-001" in r.stderr


def test_all_record_problems_are_printed(docs):
    body = ".. threat:: a\n   :id: THREAT-WRONG-001\n\n.. threat:: b\n   :id: THREAT-MY-BOX-9\n\n.. threat:: c\n   :status: open\n"
    put(docs, {"security/threat-model/my-box.rst": body})

    r = cli(docs)

    errs = [ln for ln in r.stderr.splitlines() if ln.startswith("ERROR")]
    assert len(errs) == 3, r.stderr


def test_counts_line_printed_even_when_errors_exist(docs):
    r = cli(docs, feat="FEAT-NOPE")

    assert "3 threats, 1 risks, 1 review records" in r.stdout


def test_missing_security_dir_reports_zero_records(tmp_path):
    d = tmp_path / "docs"
    put(d, {"specs/f.rst": SPEC, "architecture/c.rst": ARCH})

    r = cli(d)

    assert r.returncode == 0, r.stderr
    assert "0 threats, 0 risks, 0 review records" in r.stdout


def test_review_records_count_only_rows_starting_with_run_id(docs):
    rows = REVIEWS + "   * - deadbeef\n     - post\n     - 1\n     - b..c\n     - 0\n     - clean\n   * - notarun\n     - post\n"
    put(docs, {"security/reviews.rst": rows})

    r = cli(docs)

    assert "2 review records" in r.stdout

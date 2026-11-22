# [origin ref=llm-dsl-2zv1.5 req=REQ-SECURITY-REVIEW-009 c4=sdd_skills/security_review]
#   [intent]Tests security_gate.py append-only against temp git repos, one test per failure case plus a clean pass and the real repository.[/intent]
# [/origin]

import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "security_gate.py"
sys.path.insert(0, str(ROOT / "scripts"))
import security_gate_lib as lib

RUN = "aaaaaaaa"
TM = "docs/source/security/threat-model/my_box.rst"
RISKS = "docs/source/security/accepted-risks.rst"
REVS = "docs/source/security/reviews.rst"
HEAD_ROW = ("Run", "Stage", "Review", "Base", "Range", "Tree", "Protected", "Findings", "Outcome")


def threat(n=1, status="open", extra="", sup="", box="MY-BOX"):
    s = f"   :supersedes: {sup}\n" if sup else ""
    return f".. threat:: t{n}\n   :id: THREAT-{box}-{n:03d}\n   :status: {status}\n{extra}{s}   :links: REQ-X-001\n\n"


def risk(n=1, why="because"):
    return f".. risk:: r{n}\n   :id: RISK-MY-BOX-{n:03d}\n   :rationale: {why}\n\n"


def dec(run=RUN, who="operator"):
    return f"   :decided_by: {who}\n   :run: {run}\n"


def tm(*threats):
    return "Threats\n=======\n\n" + "".join(threats)


def reviews(rows):
    out = ["Reviews", "=======", "", ".. list-table::", "   :header-rows: 1", ""]
    for r in [HEAD_ROW] + rows:
        out += [f"   * - {r[0]}"] + [f"     - {v}" for v in r[1:]]
    return "\n".join(out) + "\n"


def rrow(review="1", stage="design", outcome="ok", run=RUN):
    return (run, stage, review, "-", "a..b", "-", "-", "0", outcome)


def g(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


def put(repo, rel, text):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit(repo, msg="c"):
    g(repo, "add", "-A")
    g(repo, "commit", "-qm", msg)
    return g(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    g(tmp_path, "init", "-q")
    g(tmp_path, "config", "user.email", "t@t")
    g(tmp_path, "config", "user.name", "t")
    put(tmp_path, TM, tm(threat(1), threat(2, "noted", dec())))
    put(tmp_path, RISKS, "Risks\n=====\n\n" + risk(1))
    put(tmp_path, REVS, reviews([rrow("1"), rrow("2")]))
    return tmp_path


def run_ao(repo, since=None, run=RUN):
    cmd = [sys.executable, str(GATE), "append-only", "--run", run, "--repo", str(repo)] + (["--since", since] if since else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stderr


def expect_fail(repo, since, *words):
    rc, err = run_ao(repo, since)
    assert rc == 1, err
    for w in words:
        assert w in err, err


def test_clean_pass_with_additions(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3))
    put(repo, RISKS, (repo / RISKS).read_text() + risk(2))
    put(repo, REVS, reviews([rrow("1"), rrow("2"), rrow("3")]))
    commit(repo)
    assert run_ao(repo, b) == (0, "")


def test_threat_removed(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(2, "noted", dec())))
    commit(repo)
    expect_fail(repo, b, "THREAT-MY-BOX-001", b[:8])


def test_risk_removed(repo):
    b = commit(repo)
    put(repo, RISKS, "Risks\n=====\n")
    commit(repo)
    expect_fail(repo, b, "RISK-MY-BOX-001", "disappeared")


def test_risk_rationale_changed(repo):
    b = commit(repo)
    put(repo, RISKS, "Risks\n=====\n\n" + risk(1, "different"))
    commit(repo)
    expect_fail(repo, b, "RISK-MY-BOX-001", "rationale")


def test_legacy_decision_removed(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1), threat(2, "noted")))
    commit(repo)
    expect_fail(repo, b, "THREAT-MY-BOX-002", "decision entry")


def test_legacy_decision_altered(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1), threat(2, "noted", dec(who="agent"))))
    commit(repo)
    expect_fail(repo, b, "THREAT-MY-BOX-002", "decision entry")


def test_decisions_list_entry_altered(repo):
    e1, e2 = 'run=aaaaaaaa decided_by=operator answer="yes"', 'run=bbbbbbbb decided_by=operator answer="no"'
    put(repo, TM, tm(threat(1, "noted", f"   :decisions: {e1}; {e2}\n")))
    b = commit(repo)
    put(repo, TM, tm(threat(1, "noted", f'   :decisions: run=aaaaaaaa decided_by=operator answer="changed"; {e2}\n')))
    commit(repo)
    expect_fail(repo, b, "THREAT-MY-BOX-001", "run=aaaaaaaa")


def test_decisions_list_entry_appended_passes(repo):
    e1, e2 = 'run=bbbbbbbb decided_by=operator answer="no"', 'run=aaaaaaaa decided_by=operator answer="ok"'
    put(repo, TM, tm(threat(1, "noted", f"   :decisions: {e1}\n")))
    b = commit(repo)
    put(repo, TM, tm(threat(1, "noted", f"   :decisions: {e1}; {e2}\n")))
    commit(repo)
    assert run_ao(repo, b)[0] == 0


def test_status_changed_without_decision(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, "accepted"), threat(2, "noted", dec())))
    commit(repo)
    expect_fail(repo, b, "THREAT-MY-BOX-001", "status changed")


def test_status_changed_with_decision_for_other_run(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, "accepted", dec("bbbbbbbb")), threat(2, "noted", dec())))
    commit(repo)
    expect_fail(repo, b, "THREAT-MY-BOX-001", "status changed")


def test_status_changed_with_decision_for_run_passes(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, "accepted", dec()), threat(2, "noted", dec())))
    commit(repo)
    assert run_ao(repo, b)[0] == 0


def test_review_row_removed(repo):
    b = commit(repo)
    put(repo, REVS, reviews([rrow("2")]))
    commit(repo)
    expect_fail(repo, b, "review=1", "removed")


def test_review_row_altered(repo):
    b = commit(repo)
    put(repo, REVS, reviews([rrow("1", outcome="rewritten"), rrow("2")]))
    commit(repo)
    expect_fail(repo, b, "review=1", "altered")


def test_review_row_duplicated(repo):
    b = commit(repo)
    put(repo, REVS, reviews([rrow("1"), rrow("2"), rrow("2", outcome="again")]))
    commit(repo)
    expect_fail(repo, b, "review=2", "2 times")


def test_supersedes_target_missing(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, sup="THREAT-MY-BOX-099"))
    commit(repo)
    expect_fail(repo, b, "THREAT-MY-BOX-003", "THREAT-MY-BOX-099", "does not exist")


def test_supersedes_other_container(repo):
    b = commit(repo)
    put(repo, "docs/source/security/threat-model/other.rst", "T\n=\n\n" + threat(3, sup="THREAT-MY-BOX-001", box="OTHER"))
    commit(repo)
    expect_fail(repo, b, "THREAT-OTHER-003", "another container")


def test_supersedes_two_successors(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, sup="THREAT-MY-BOX-001") + threat(4, sup="THREAT-MY-BOX-001"))
    commit(repo)
    expect_fail(repo, b, "THREAT-MY-BOX-001", "2 successors")


def test_supersedes_cycle(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, sup="THREAT-MY-BOX-003"), threat(2, "noted", dec()), threat(3, sup="THREAT-MY-BOX-001")))
    commit(repo)
    expect_fail(repo, b, "cycle")


def test_superseding_status_differs_without_decision(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, "noted", sup="THREAT-MY-BOX-001"))
    commit(repo)
    expect_fail(repo, b, "THREAT-MY-BOX-003", "different status")


def test_superseding_status_differs_with_decision_passes(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, "noted", dec(), sup="THREAT-MY-BOX-001"))
    commit(repo)
    assert run_ao(repo, b)[0] == 0


def test_superseding_inherits_status_passes(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, sup="THREAT-MY-BOX-001"))
    commit(repo)
    assert run_ao(repo, b)[0] == 0


def test_failure_is_checked_against_every_since_commit(repo):
    b1 = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3))
    b2 = commit(repo)
    put(repo, TM, tm(threat(1), threat(2, "noted", dec())))
    commit(repo)
    rc, err = run_ao(repo, f"{b1},{b2}")
    assert rc == 1 and "THREAT-MY-BOX-003" in err and b2[:8] in err and f"since {b1[:8]}" not in err


def test_added_review_column_is_not_an_alteration(repo):
    old = "Reviews\n=======\n\n.. list-table::\n   :header-rows: 1\n\n   * - Run\n     - Stage\n     - Review\n     - Range\n     - Findings\n     - Outcome\n   * - aaaaaaaa\n     - design\n     - 1\n     - a..b\n     - 0\n     - ok\n"
    put(repo, REVS, old)
    b = commit(repo)
    put(repo, REVS, reviews([rrow("1")]))
    commit(repo)
    assert run_ao(repo, b)[0] == 0


def test_unknown_since_commit_fails(repo):
    commit(repo)
    expect_fail(repo, "deadbeef", "deadbeef")


def test_default_since_uses_latest_review_commit(repo):
    commit(repo)
    put(repo, REVS, reviews([rrow("1"), rrow("2"), rrow("3")]))
    gate = commit(repo, "gate")
    put(repo, TM, tm(threat(2, "noted", dec())))
    commit(repo, "later")
    assert lib.latest_review_commit(repo, RUN) == gate
    assert lib.default_since(repo, RUN) == [gate]
    rc, err = run_ao(repo)
    assert rc == 1 and "THREAT-MY-BOX-001" in err


def test_run_87708f1a_records_are_append_only_since_a429fd8():
    rc, err = run_ao(ROOT, "a429fd8", "87708f1a")
    assert (rc, err) == (0, "")

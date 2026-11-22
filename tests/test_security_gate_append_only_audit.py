# [origin ref=llm-dsl-2zv1.6 req=REQ-SECURITY-REVIEW-009 c4=sdd_skills/security_review]
#   [intent]Audits security_gate.py append-only with evasion attempts (column games, id moves, reflows, decision forms, supersedes shapes, duplicate rows, several --since, deleted files) in real temp git repos.[/intent]
# [/origin]

import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "security_gate.py"
sys.path.insert(0, str(ROOT / "scripts"))

RUN = "aaaaaaaa"
TM = "docs/source/security/threat-model/my_box.rst"
TM2 = "docs/source/security/threat-model/other_box.rst"
RISKS = "docs/source/security/accepted-risks.rst"
REVS = "docs/source/security/reviews.rst"
HEAD = ["Run", "Stage", "Review", "Base", "Range", "Tree", "Protected", "Findings", "Outcome"]


def threat(n=1, status="open", extra="", sup="", box="MY-BOX", tid=None):
    s = f"   :supersedes: {sup}\n" if sup else ""
    tid = tid or f"THREAT-{box}-{n:03d}"
    return f".. threat:: t{n}\n   :id: {tid}\n   :status: {status}\n{extra}{s}   :links: REQ-X-001\n\n"


def risk(n=1, body="   :rationale: because we accept it\n"):
    return f".. risk:: r{n}\n   :id: RISK-MY-BOX-{n:03d}\n{body}\n"


def dec(run=RUN, who="operator"):
    return f"   :decided_by: {who}\n   :run: {run}\n"


def tm(*threats):
    return "Threats\n=======\n\n" + "".join(threats)


def table(head, rows):
    out = ["Reviews", "=======", "", ".. list-table::", "   :header-rows: 1", ""]
    for r in [head] + rows:
        out += [f"   * - {r[0]}"] + [f"     - {v}" for v in r[1:]]
    return "\n".join(out) + "\n"


def row(review="1", outcome="ok", stage="design"):
    return dict(zip(HEAD, [RUN, stage, review, "-", "a..b", "-", "-", "0", outcome]))


def reviews(rows, head=HEAD):
    return table(head, [[r[h] for h in head] for r in rows])


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
    put(tmp_path, REVS, reviews([row("1"), row("2")]))
    return tmp_path


def run_ao(repo, since=None, run=RUN):
    cmd = [sys.executable, str(GATE), "append-only", "--run", run, "--repo", str(repo)] + (["--since", since] if since else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stderr


def fails(repo, since, *words):
    rc, err = run_ao(repo, since)
    assert rc == 1, err
    for w in words:
        assert w in err, err


def passes(repo, since):
    assert run_ao(repo, since) == (0, "")


def rev_change(repo, new_text):
    b = commit(repo)
    put(repo, REVS, new_text)
    commit(repo)
    return b


def test_clean_control_unchanged_passes(repo):
    b = commit(repo)
    g(repo, "commit", "-q", "--allow-empty", "-m", "e")
    passes(repo, b)


@pytest.mark.parametrize("drop", ["Outcome", "Base", "Findings", "Range", "Stage", "Review"])
def test_dropping_a_column_is_detected(repo, drop):
    head = [h for h in HEAD if h != drop]
    b = rev_change(repo, reviews([row("1"), row("2")], head))
    fails(repo, b, "review row run=")


def test_dropping_column_whose_old_value_was_dash(repo):
    head = [h for h in HEAD if h != "Tree"]
    b = rev_change(repo, reviews([row("1"), row("2")], head))
    fails(repo, b, "altered")


def test_renaming_a_column_header_is_detected(repo):
    t = reviews([row("1"), row("2")]).replace("Outcome", "Result")
    b = rev_change(repo, t)
    fails(repo, b, "altered")


def test_reordering_headers_only_moves_values_and_is_detected(repo):
    t = reviews([row("1"), row("2")]).replace("Findings", "TMP").replace("Outcome", "Findings").replace("TMP", "Outcome")
    b = rev_change(repo, t)
    fails(repo, b, "altered")


def test_consistent_column_reorder_is_not_an_alteration(repo):
    head = ["Run", "Stage", "Review", "Outcome", "Findings", "Range", "Base", "Tree", "Protected"]
    b = rev_change(repo, reviews([row("1"), row("2")], head))
    passes(repo, b)


def test_adding_a_new_column_passes(repo):
    head = HEAD + ["Notes"]
    rows = [dict(row("1"), Notes="n"), dict(row("2"), Notes="n")]
    b = rev_change(repo, reviews(rows, head))
    passes(repo, b)


def test_dropping_all_headers_misaligns_and_is_detected(repo):
    lines = reviews([row("1"), row("2")]).splitlines()
    i = lines.index("   * - Run")
    j = lines.index("   * - " + RUN)
    t2 = "\n".join(lines[:i] + lines[j:]) + "\n"
    b = rev_change(repo, t2)
    fails(repo, b, "run=")


def test_threat_id_case_change_is_detected(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, tid="THREAT-my-box-001"), threat(2, "noted", dec())))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001", "disappeared")


@pytest.mark.xfail(strict=True, reason="append-only keys records by id only; moving THREAT-MY-BOX-001 into another container's file passes")
def test_threat_moved_to_other_container_file_is_detected(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(2, "noted", dec())))
    put(repo, TM2, tm(threat(1, tid="THREAT-MY-BOX-001")))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001")


def test_threat_moved_and_renamed_to_other_container_is_detected(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(2, "noted", dec())))
    put(repo, TM2, tm(threat(1, box="OTHER-BOX")))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001", "disappeared")


def test_risk_rationale_whitespace_reflow_passes(repo):
    put(repo, RISKS, "R\n=\n\n" + risk(1, "   :rationale: one two three four\n"))
    b = commit(repo)
    put(repo, RISKS, "R\n=\n\n" + risk(1, "   :rationale: one two\n       three four\n"))
    commit(repo)
    passes(repo, b)


def test_risk_rationale_wording_change_fails(repo):
    put(repo, RISKS, "R\n=\n\n" + risk(1, "   :rationale: one two three four\n"))
    b = commit(repo)
    put(repo, RISKS, "R\n=\n\n" + risk(1, "   :rationale: one two three five\n"))
    commit(repo)
    fails(repo, b, "RISK-MY-BOX-001", "rationale")


def test_risk_rationale_blanked_fails(repo):
    b = commit(repo)
    put(repo, RISKS, "R\n=\n\n" + risk(1, ""))
    commit(repo)
    fails(repo, b, "RISK-MY-BOX-001", "rationale")


E1 = 'run=aaaaaaaa decided_by=operator answer="yes"'
E2 = 'run=bbbbbbbb decided_by=operator answer="no"'


def test_decisions_reordered_passes(repo):
    put(repo, TM, tm(threat(1, "noted", f"   :decisions: {E1}; {E2}\n")))
    b = commit(repo)
    put(repo, TM, tm(threat(1, "noted", f"   :decisions: {E2}; {E1}\n")))
    commit(repo)
    passes(repo, b)


def test_decision_answer_edited_fails(repo):
    put(repo, TM, tm(threat(1, "noted", f"   :decisions: {E1}; {E2}\n")))
    b = commit(repo)
    put(repo, TM, tm(threat(1, "noted", f'   :decisions: {E1}; run=bbbbbbbb decided_by=operator answer="NO!"\n')))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001", "run=bbbbbbbb")


def test_decision_answer_removed_fails(repo):
    put(repo, TM, tm(threat(1, "noted", f"   :decisions: {E1}\n")))
    b = commit(repo)
    put(repo, TM, tm(threat(1, "noted", "   :decisions: run=aaaaaaaa decided_by=operator\n")))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001", "run=aaaaaaaa")


def test_decision_decided_by_changed_fails(repo):
    put(repo, TM, tm(threat(1, "noted", f"   :decisions: {E1}\n")))
    b = commit(repo)
    put(repo, TM, tm(threat(1, "noted", '   :decisions: run=aaaaaaaa decided_by=agent answer="yes"\n')))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001", "run=aaaaaaaa")


def test_legacy_pair_converted_to_decisions_entry_passes(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1), threat(2, "noted", f"   :decisions: run={RUN} decided_by=operator\n")))
    commit(repo)
    passes(repo, b)


def test_legacy_pair_converted_to_other_run_fails(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1), threat(2, "noted", "   :decisions: run=bbbbbbbb decided_by=operator\n")))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-002", "decision entry")


def test_legacy_pair_converted_to_agent_fails(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1), threat(2, "noted", f"   :decisions: run={RUN} decided_by=agent\n")))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-002", "decision entry")


def test_status_flip_with_decisions_entry_for_other_run_fails(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, "accepted", "   :decisions: run=bbbbbbbb decided_by=operator\n"), threat(2, "noted", dec())))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001", "status changed")


def test_status_flip_with_agent_decision_for_this_run_fails(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, "accepted", f"   :decisions: run={RUN} decided_by=agent\n"), threat(2, "noted", dec())))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001", "status changed")


def test_status_flip_with_decisions_entry_for_this_run_passes(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, "accepted", f"   :decisions: run={RUN} decided_by=operator answer=\"ok\"\n"), threat(2, "noted", dec())))
    commit(repo)
    passes(repo, b)


def test_superseding_record_in_other_container_file_fails(repo):
    b = commit(repo)
    put(repo, TM2, tm(threat(3, box="OTHER-BOX", sup="THREAT-MY-BOX-001")))
    commit(repo)
    fails(repo, b, "THREAT-OTHER-BOX-003", "another container")


def test_two_successors_fails(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, sup="THREAT-MY-BOX-001") + threat(4, sup="THREAT-MY-BOX-001"))
    commit(repo)
    fails(repo, b, "2 successors", "THREAT-MY-BOX-003", "THREAT-MY-BOX-004")


def test_three_cycle_fails(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, sup="THREAT-MY-BOX-003"), threat(2, "noted", dec(), sup="THREAT-MY-BOX-001"), threat(3, sup="THREAT-MY-BOX-002")))
    commit(repo)
    fails(repo, b, "cycle")


def test_self_supersede_fails(repo):
    b = commit(repo)
    put(repo, TM, tm(threat(1, sup="THREAT-MY-BOX-001"), threat(2, "noted", dec())))
    commit(repo)
    fails(repo, b, "cycle")


def test_superseding_different_status_without_decision_fails(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, "mitigated", sup="THREAT-MY-BOX-001"))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-003", "different status")


def test_superseding_different_status_with_decision_for_other_run_fails(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, "mitigated", dec("bbbbbbbb"), sup="THREAT-MY-BOX-001"))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-003", "different status")


def test_superseding_different_status_with_decision_for_run_passes(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, "mitigated", dec(), sup="THREAT-MY-BOX-001"))
    commit(repo)
    passes(repo, b)


def test_duplicate_review_key_in_same_commit_fails(repo):
    b = rev_change(repo, reviews([row("1"), row("2"), row("2")]))
    fails(repo, b, "review=2", "2 times")


def test_duplicate_review_key_with_old_row_unchanged_still_fails(repo):
    b = rev_change(repo, reviews([row("1"), row("2"), row("1", outcome="evil")]))
    fails(repo, b, "review=1", "2 times")


def test_review_row_deleted_and_readded_with_other_values_fails(repo):
    b = rev_change(repo, reviews([row("2"), row("1", outcome="rewritten")]))
    fails(repo, b, "review=1", "altered")


def test_review_row_reordered_passes(repo):
    b = rev_change(repo, reviews([row("2"), row("1")]))
    passes(repo, b)


def test_review_row_stage_changed_reports_removed(repo):
    b = rev_change(repo, reviews([row("1", stage="post"), row("2")]))
    fails(repo, b, "stage=design", "removed")


def test_since_second_sha_fails_and_is_named(repo):
    put(repo, TM, tm(threat(1), threat(2, "noted", dec()), threat(5)))
    b1 = commit(repo)
    put(repo, TM, tm(threat(1), threat(2, "noted", dec())))
    b2 = commit(repo)
    put(repo, TM, tm(threat(1), threat(2, "noted", dec())) + "\n")
    commit(repo)
    rc, err = run_ao(repo, f"{b2},{b1}")
    assert rc == 1 and f"since {b1[:8]}" in err and f"since {b2[:8]}" not in err and "THREAT-MY-BOX-005" in err


def test_since_first_sha_fails_and_is_named(repo):
    b0 = commit(repo)
    put(repo, TM, tm(threat(1), threat(2, "noted", dec()), threat(5)))
    b1 = commit(repo)
    put(repo, TM, tm(threat(2, "noted", dec()), threat(5)))
    commit(repo)
    rc, err = run_ao(repo, f"{b1},{b0}")
    assert rc == 1 and f"since {b1[:8]}" in err and f"since {b0[:8]}" in err


def test_since_with_bad_sha_among_good_names_it(repo):
    b = commit(repo)
    rc, err = run_ao(repo, f"{b},cafebabe")
    assert rc == 1 and "cafebabe" in err and f"since {b[:8]}" not in err


def test_since_several_clean_passes(repo):
    b1 = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3))
    b2 = commit(repo)
    passes(repo, f"{b1},{b2}")


def test_security_dir_deleted_entirely_names_every_id(repo):
    b = commit(repo)
    g(repo, "rm", "-rq", "docs/source/security")
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001", "THREAT-MY-BOX-002", "RISK-MY-BOX-001", "review=1", "review=2")


def test_threat_file_deleted_names_its_ids(repo):
    b = commit(repo)
    g(repo, "rm", "-q", TM)
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-001", "THREAT-MY-BOX-002")


def test_reviews_file_deleted_names_rows(repo):
    b = commit(repo)
    g(repo, "rm", "-q", REVS)
    commit(repo)
    fails(repo, b, "review=1", "review=2", "removed")


def test_uncommitted_working_tree_deletion_is_not_trusted(repo):
    b = commit(repo)
    (repo / TM).write_text(tm(threat(2, "noted", dec())))
    rc, err = run_ao(repo, b)
    assert rc == 0


def test_supersedes_target_missing_fails(repo):
    b = commit(repo)
    put(repo, TM, (repo / TM).read_text() + threat(3, sup="THREAT-MY-BOX-099"))
    commit(repo)
    fails(repo, b, "THREAT-MY-BOX-003", "THREAT-MY-BOX-099", "does not exist")

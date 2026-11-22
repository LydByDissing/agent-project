# [origin ref=llm-dsl-2zv1.12,llm-dsl-2zv1.16 req=REQ-SECURITY-REVIEW-001,REQ-SECURITY-REVIEW-002,REQ-SECURITY-REVIEW-004,REQ-SECURITY-REVIEW-005,REQ-SECURITY-REVIEW-011,REQ-SECURITY-REVIEW-012 c4=sdd_skills/security_review]
#   [intent]Audit that following skills/security-review/SKILL.md literally yields records the real security gate accepts, that every acceptance clause has an instruction, and that no instruction contradicts the gate, the analyst agent or the safety rules.[/intent]
# [/origin]

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = Path(os.environ.get("SECREV_SKILL_PATH", ROOT / "skills" / "security-review" / "SKILL.md"))
ANALYST = ROOT / "agents" / "security-analyst.md"
GATE = ROOT / "scripts" / "security_gate.py"
FEAT = "FEAT-OPERATOR-EDU"
REQ = "REQ-OPERATOR-EDU-004"
RUN = "87708f1a"
EPIC = "EPIC-1"


def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def step(t: str, n: int) -> str:
    m = re.search(rf"^## Step {n}\b.*$", t, re.M)
    assert m is not None, f"no heading for step {n}"
    nxt = re.search(r"^## ", t[m.end():], re.M)
    return t[m.start(): m.end() + nxt.start() if nxt else len(t)]


def section(t: str, name: str) -> str:
    m = re.search(rf"^## {re.escape(name)}\b.*$", t, re.M)
    assert m is not None, f"no section {name}"
    nxt = re.search(r"^## ", t[m.end():], re.M)
    return t[m.start(): m.end() + nxt.start() if nxt else len(t)]


def fences(sec: str, lang: str | None = None) -> list[str]:
    out = []
    for m in re.finditer(r"^[ ]*```([a-z]*)\n(.*?)^[ ]*```", sec, re.M | re.S):
        if lang is None or m.group(1) == lang:
            out.append(m.group(2))
    return out


def dedent(block: str) -> str:
    lines = block.splitlines()
    ind = min((len(x) - len(x.lstrip()) for x in lines if x.strip()), default=0)
    return "\n".join(x[ind:] for x in lines) + "\n"


def has(sec: str, pat: str) -> bool:
    return re.search(pat, sec, re.I | re.S) is not None


def mutate(sec: str, pat: str) -> str:
    out = re.sub(pat, "XXXX", sec, flags=re.I | re.S)
    assert out != sec, f"mutation /{pat}/ changed nothing"
    return out


# ---------------------------------------------------------------- requirement trace

# (requirement, clause, step or section locator, pattern)
TRACE = [
    ("001", "per-container trust boundaries list written", ("step", 6), r"trust boundaries"),
    ("002", "add-requirement findings go to the docs skill; sdd increments reset-count", ("step", 13), r"docs skill.{0,300}reset-count|reset-count.{0,300}docs skill"),
    ("002", "severity persisted on the written threat", ("step", 6), r":severity:"),
    ("011", "epic carries exactly one base= label (others removed, confirmed one added)", ("step", 1), r"label remove.{0,200}base=.{0,300}label add.{0,80}base=|label add.{0,80}base=.{0,300}label remove"),
    ("010", "commit message and [security] block temp files created before redact-check", ("step", 11), r"COMMIT_MSG_FILE=\$\(mktemp.{0,600}SECURITY_BLOCK_FILE=\$\(mktemp|SECURITY_BLOCK_FILE=\$\(mktemp.{0,600}COMMIT_MSG_FILE=\$\(mktemp"),
    ("001", "input = spec + ADRs + threat model + diff of docs/source and SKILL.md from base", ("step", 2), r"stage=design.{1,200}docs/source/\*\*.{1,60}skills/\*\*/SKILL\.md.{1,120}feature spec.{1,40}ADRs.{1,80}threat model"),
    ("001", "STRIDE at design", ("intro",), r"STRIDE"),
    ("001", "does not review application code at design", ("intro",), r"Does not review application code"),
    ("001", "plan does not start until gate passed (check exit 0 required)", ("step", 13), r"Exit 0 is required to advance"),
    ("001", "advance to plan only after design check", ("step", 13), r"stage=design.{1,200}advance to plan"),
    ("002", "every open threat listed with severity, STRIDE, C4 element, mitigation", ("step", 7), r"every\*\* open threat.{1,400}table \(id, severity, STRIDE,\s+C4 element, anchor, proposed mitigation\)|table \(id, severity, STRIDE,\s+C4 element.{1,200}every\*\* open threat"),
    ("002", "three design options add requirement / accept risk / note", ("step", 7), r"stage=design.{1,100}add requirement.{1,300}accept risk.{1,200}note"),
    ("002", "accept risk -> RISK need with operator rationale", ("step", 7), r"risk.{1,60}need.{1,200}accepted-risks\.rst.{1,200}rationale"),
    ("002", "add requirement -> status stays open, reset to docs", ("step", 13), r"add requirement.{1,200}reset to docs.{1,60}status stays `open`"),
    ("002", "re-review runs incrementally after docs reset", ("step", 13), r"review runs again\s+incrementally"),
    ("002", "no add requirement -> advance to plan", ("step", 13), r"no \"add requirement\" decision and check ok"),
    ("004", "post stage runs after arch-review and uses OWASP", ("intro",), r"stage=post.{1,300}arch-review.{1,200}OWASP"),
    ("004", "post input is run code diff from base", ("step", 2), r"stage=post.{1,200}\$BASE\.\.HEAD.{1,100}code"),
    ("004", "mitigated needs file:line", ("step", 8), r"file:line"),
    ("004", "mitigated needs covering test id", ("step", 8), r"covering test id"),
    ("004", "sabotage in throwaway worktree, test must fail", ("step", 8), r"throwaway git worktree.{1,300}fails"),
    ("004", "real working tree clean after sabotage", ("step", 8), r"git status --porcelain.{1,80}nothing"),
    ("004", "disabling patch recorded on the threat", ("step", 8), r"disabling patch.{1,80}recorded on the threat"),
    ("004", "without evidence status stays open", ("step", 8), r"Without it the\s+status stays\s+`open`"),
    ("004", "operator confirms each proposed mitigated", ("step", 7), r"each proposed `mitigated`.{1,60}\*\*confirm\*\*.{1,20}\*\*reject\*\*"),
    ("004", "epic closes only after the gate (skill does not close)", ("step", 13), r"you do not close the epic"),
    ("005", "post options fix / accept risk / note / revise docs", ("step", 7), r"stage=post.{1,60}\*\*fix\*\*.{1,60}\*\*accept risk\*\*.{1,60}\*\*note\*\*.{1,60}\*\*revise docs\*\*"),
    ("005", "coder issue [out] = finding files + one new test", ("step", 9), r"only the files named in the finding plus \*\*one new test file\*\*"),
    ("005", "[out] never in protected set, whatever finding names", ("step", 9), r"never includes any path of the protected\s+set.{1,700}whatever the finding names"),
    ("005", "orchestrator itself runs full suites", ("step", 9), r"\*\*you\*\* verify.{1,300}Run the full test suites yourself"),
    ("005", "orchestrator checks diff in scope", ("step", 9), r"Scope\.\*\*.{1,200}`\[out\]` paths"),
    ("005", "sabotage that new test fails without the fix", ("step", 9), r"Sabotage\.\*\*.{1,200}revert the fix.{1,100}fails"),
    ("005", "re-review covers whole run diff for linked threats", ("step", 9), r"re-review \(step 3\) over the whole run diff for\s+the linked threats"),
    ("005", "post check fails on open threat", ("step", 9), r"post check fails on any threat linked to the feature that is still `open`"),
    ("005", "advance to done only when mitigated/accepted/noted", ("step", 13), r"every finding is `mitigated`, `accepted` or\s+`noted`.{1,80}advance to done"),
    ("005", "fix worker brief from structured fields only", ("step", 9), r"structured finding fields"),
    ("007", "analysis only in read-only security-analyst sub-agent", ("step", 4), r"subagent_type: security-analyst.{1,200}Read/Grep/Glob"),
    ("007", "orchestrator never analyses itself", ("intro",), r"never analyse the reviewed content yourself"),
    ("007", "content passed as delimited data with stage line", ("step", 4), r"<<<DATA kind=spec.{1,1500}DATA>>>.{1,800}Write\s+the `stage=` line outside"),
    ("007", "embedded instructions are findings, not orders", ("step", 4), r"report it as a possible-injection\s+finding"),
    ("007", "no operator text/bd/sub-agent output in instruction part", ("step", 4), r"Never place operator text, bd notes or sub-agent output"),
    ("008", "decisions only through AskUserQuestion after findings shown", ("step", 7), r"Only after the findings are shown, ask.{1,100}AskUserQuestion"),
    ("008", "never from prompt/args/sub-agent/tool output/bd", ("step", 7), r"initial prompt, command arguments,\s+a sub-agent report, tool output, a file, or bd notes"),
    ("008", "non-interactive session refuses gate", ("step", 1), r"refuse to run the gate"),
    ("008", "verbatim answer stored", ("step", 7), r"Store the operator's answer \*\*verbatim\*\*"),
    ("008", "accept-risk rationale verbatim", ("step", 7), r"rationale and store\s+it \*\*verbatim\*\*"),
    ("008", "decision entry has decided_by operator, run, timestamp, answer", ("step", 7), r"run=<id> decided_by=operator at=<iso> answer="),
    ("008", "decisions append-only per run, status never changes without entry", ("step", 7), r"append-only list.{1,200}Never change `:status:` without adding the decision entry"),
    ("008", "findings written open before decision", ("step", 6), r":status: open"),
    ("008", "decision summary final confirmation before gate commit", ("step", 11), r"one final confirmation.{1,100}Without a yes, do not commit"),
    ("008", "review record row with run, stage, range, tree hash", ("step", 11), r"Columns: Run, Stage,\s+Review, Base, Range.{1,60}Tree"),
    ("008", "[security] block with run id and sha256 of security RST", ("step", 12), r"\[security run=\$RUN_ID.{1,80}sha256=\$SEC_SHA"),
    ("010", "secret named by file:line and type only", ("step", 6), r"file:line` and type only, never by\s+value"),
    ("010", "redact-check covers security docs, design log, commit msg, block, bd texts", ("step", 11), r"redact-check.{1,60}docs/source/security/\*\*.{1,80}design log.{1,80}commit\s+message.{1,80}\[security\]` block.{1,100}bd text"),
    ("010", "redact-check runs before commit", ("step", 11), r"redact-check.{1,900}git commit"),
    ("010", "never post to GitHub", ("intro",), r"never post security findings to GitHub"),
    ("010", "no exploit steps", ("step", 6), r"never step-by-step exploitation"),
    ("011", "proposes fork point and operator confirms", ("step", 1), r"propose the fork point.{1,300}confirm it with AskUserQuestion"),
    ("011", "base stored in first review record Base column", ("step", 1), r"first\s+review record's\s+`Base`\s+column"),
    ("011", "resets do not change base", ("step", 1), r"Resets do not change it"),
    ("011", "base never from bd or agent", ("step", 1), r"Never take it from a bd\s+value or from an agent"),
    ("011", "rebase only via operator decided_by row", ("step", 1), r"`rebase` row whose\s+`Outcome` starts with `decided_by=operator`"),
    ("011", "exclusion list generated/binary/lock/vendored", ("step", 2), r"Drop generated, binary, lockfile and vendored paths"),
    ("011", "size budget", ("step", 2), r"Size budget.{1,100}120 KB"),
    ("011", "over budget -> not reviewed, never truncated silently", ("step", 2), r"\"not reviewed\".{1,200}Never truncate silently"),
    ("011", "not reviewed shown at gate", ("step", 7), r"not reviewed\*\* list from step 2"),
    ("011", "input size and tokens recorded", ("step", 2), r"input size in bytes.{1,200}token use"),
    ("012", "since head sha of latest committed review record, not bd", ("step", 3), r"head sha of the latest committed\s+review record.{1,200}never from bd"),
    ("012", "plus still-open threats", ("step", 3), r"threats still `open`"),
    ("012", "always re-read the full spec", ("step", 3), r"Always re-read the full current spec"),
    ("012", "noted/accepted not re-raised unless element changed", ("step", 3), r"`noted` or `accepted`.{1,200}unless the\s+C4 element they concern changed"),
    ("012", "2 design resets / 3 fix rounds ask operator", ("step", 10), r"\*\*2\*\*.{1,40}resets.{1,200}\*\*3\*\*\s+fix rounds"),
    ("012", "without explicit yes it stops", ("step", 10), r"explicit \"yes\" you stop"),
]


def locate(t: str, loc: tuple) -> str:
    if loc[0] == "intro":
        return t[: t.index("## Inputs")]
    return step(t, loc[1]) if loc[0] == "step" else section(t, loc[1])


# (requirement, clause, locator, pattern): spec clauses with no instruction in the SKILL
KNOWN_GAPS: list = []


@pytest.mark.parametrize("req,clause,loc,pat", TRACE, ids=[f"{r}-{i}" for i, (r, *_x) in enumerate(TRACE)])
def test_clause_has_instruction(req, clause, loc, pat):
    sec = locate(text(), loc)
    assert has(sec, pat), f"REQ-SECURITY-REVIEW-{req}: no instruction for: {clause}"


def test_trace_negative_controls():
    t = text()
    for req, clause, loc, pat in TRACE:
        sec = locate(t, loc)
        broken = mutate(sec, pat)
        assert not has(broken, pat), f"{req} {clause}: control mutation did not remove it"


def test_trace_covers_all_audited_requirements():
    assert {r for r, *_ in TRACE} == {"001", "002", "004", "005", "007", "008", "010", "011", "012"}
    assert len(TRACE) >= 60


# ---------------------------------------------------------------- sample extraction

def sample_threat_open() -> str:
    return dedent(fences(step(text(), 6), "rst")[0])


def sample_threat_decided() -> str:
    return dedent(fences(step(text(), 7), "rst")[-1])


def sample_row_cells() -> list[str]:
    blk = [b for b in fences(step(text(), 11), "rst") if "* - " in b][0]
    cells = []
    for ln in blk.splitlines():
        s = ln.strip()
        if s.startswith("* - "):
            cells.append(s[4:])
        elif s.startswith("- "):
            cells.append(s[2:])
    return cells


def sample_commit_message() -> str:
    blk = [b for b in fences(step(text(), 11)) if b.startswith("   security(") or b.lstrip().startswith("security(")][0]
    return dedent(blk)


def sample_findings() -> list[dict]:
    a = ANALYST.read_text(encoding="utf-8")
    m = re.search(r"```json\n(.*?)```", a, re.S)
    assert m is not None
    return json.loads(m.group(1))


def render_row(cells: list[str]) -> str:
    out = [f"   * - {cells[0]}"] + [f"     - {c}" for c in cells[1:]]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- fixture repo

def git(repo: Path, *a: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"git {a}: {r.stderr}"
    return r.stdout.strip()


def gate(repo: Path, *a: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GATE), *a], capture_output=True, text=True, cwd=repo)


def write(repo: Path, rel: str, body: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


SPEC = f""".. feat:: Operator education
   :id: {FEAT}
   :status: approved

.. req:: Start endpoint origin
   :id: {REQ}
   :links: {FEAT}
"""
ARCH = "Components\n==========\n\nlearn_server\n~~~~~~~~~~~~\n\nsecurity_review\n~~~~~~~~~~~~~~~\n"
THREATS = "Learn Server threats\n====================\n\nTrust boundaries\n----------------\n\n- Operator and server.\n\nThreats\n-------\n\n"
REVIEWS_HEAD = """Security Reviews
================

.. list-table::
   :header-rows: 1

   * - Run
     - Stage
     - Review
     - Base
     - Range
     - Tree
     - Protected
     - Findings
     - Outcome
"""
RISKS = "Accepted risks\n==============\n\n"


class Flow:
    def __init__(self, tmp: Path):
        self.repo = tmp / "repo"
        self.repo.mkdir()
        r = self.repo
        git(r, "init", "-q", "-b", "main")
        write(r, "docs/source/specs/features/f.rst", SPEC)
        write(r, "docs/source/architecture/c.rst", ARCH)
        write(r, "docs/source/security/threat-model/learn_server.rst", THREATS)
        write(r, "docs/source/security/reviews.rst", REVIEWS_HEAD)
        write(r, "docs/source/security/accepted-risks.rst", RISKS)
        write(r, "skills/x/SKILL.md", "base skill\n")
        git(r, "add", "-A")
        git(r, "commit", "-qm", "base")
        self.base = git(r, "rev-parse", "HEAD")
        git(r, "checkout", "-q", "-b", "feat")
        write(r, "docs/source/specs/features/f.rst", SPEC + "\n   Added text.\n")
        git(r, "commit", "-qam", "docs change")
        self.prev = self.base

    @property
    def tf(self) -> Path:
        return self.repo / "docs/source/security/threat-model/learn_server.rst"

    def epic(self, base: str | None = None) -> str:
        p = self.repo.parent / "epic.json"
        p.write_text(json.dumps([{"id": EPIC, "labels": [f"run={RUN}", f"base={base or self.base}", f"feat={FEAT}"]}]))
        return str(p)

    def check(self, stage: str, base: str | None = None) -> subprocess.CompletedProcess:
        return gate(self.repo, "check", "--feature", FEAT, "--stage", stage, "--epic", EPIC, "--main", "main", "--repo", str(self.repo), "--bd-json", self.epic(base))

    def tree(self) -> str:
        r = gate(self.repo, "tree-hash", "--feature", FEAT, "--run", RUN, "--repo", str(self.repo))
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def add_threat(self, body: str, tid: str | None = None) -> None:
        if tid:
            body = body.replace("THREAT-LEARN-SERVER-004", tid)
        self.tf.write_text(self.tf.read_text() + body + "\n")

    def replace_threat(self, body: str, old_id: str = "THREAT-LEARN-SERVER-004") -> None:
        t = self.tf.read_text()
        i = t.index(f".. threat::", max(0, t.index(f":id: {old_id}") - 200))
        j = t.find("\n.. threat::", i + 5)
        j = len(t) if j < 0 else j + 1
        self.tf.write_text(t[:i] + body + "\n" + t[j:])

    def row(self, stage: str, review: str, protected: str | None = None, outcome: str | None = None) -> None:
        cells = sample_row_cells()
        assert len(cells) == 9, cells
        head = git(self.repo, "rev-parse", "HEAD")
        cells[1], cells[2] = stage, review
        cells[3] = self.base
        cells[4] = f"{self.prev}..{head}"
        cells[5] = self.tree()
        if protected is not None:
            cells[6] = protected
        if outcome is not None:
            cells[8] = outcome
        p = self.repo / "docs/source/security/reviews.rst"
        p.write_text(p.read_text() + render_row(cells))
        self.prev = head

    def commit_security(self, stage: str, n: str) -> None:
        msg = sample_commit_message().replace("<stage>", stage).replace("<n>", n).replace("<FEAT_ID>", FEAT).replace("<RUN_ID>", RUN)
        self.msg = self.repo.parent / "msg.txt"
        self.msg.write_text(msg)
        r = gate(self.repo, "redact-check", "--paths", "docs/source/security", "--feature", FEAT, "--run", RUN, "--text-file", str(self.msg), "--repo", str(self.repo))
        assert r.returncode == 0, f"redact-check blocks the SKILL's own sample: {r.stdout}{r.stderr}"
        git(self.repo, "add", "docs/source/security")
        git(self.repo, "commit", "-qF", str(self.msg))

    def append_only(self) -> subprocess.CompletedProcess:
        return gate(self.repo, "append-only", "--run", RUN, "--repo", str(self.repo))


@pytest.fixture
def flow(tmp_path):
    f = Flow(tmp_path)
    yield f
    shutil.rmtree(tmp_path, ignore_errors=True)


def design(flow: Flow) -> None:
    flow.add_threat(sample_threat_open())
    r = gate(flow.repo, "validate", "--feature", FEAT, "--docs", str(flow.repo / "docs/source"))
    assert r.returncode == 0, f"validate fails on the SKILL's open sample: {r.stderr}"
    pre = flow.check("design")
    assert pre.returncode == 1 and "no review record" in pre.stderr
    flow.replace_threat(sample_threat_decided())
    flow.tf.parent.parent.joinpath("accepted-risks.rst").write_text(
        RISKS + f".. risk:: Local-only dev tool\n   :id: RISK-007\n   :rationale: local-only dev tool, tracked in RISK-007\n   :run: {RUN}\n   :decided_by: operator\n   :links: THREAT-LEARN-SERVER-004\n\n   Body.\n"
    )
    flow.row("design", "1", protected="-", outcome="004 accepted")
    flow.commit_security("design", "1")


# ---------------------------------------------------------------- executable samples

def test_design_flow_as_written_passes_gate(flow):
    design(flow)
    r = flow.append_only()
    assert r.returncode == 0, r.stderr
    c = flow.check("design")
    assert c.returncode == 0, c.stderr
    assert "gate script unverified (bootstrap)" in c.stdout


def test_design_flow_fails_without_decision_fields(flow):
    flow.add_threat(sample_threat_open())
    flow.row("design", "1", protected="-")
    flow.commit_security("design", "1")
    c = flow.check("design")
    assert c.returncode == 1 and "open without a decision" in c.stderr


def test_design_flow_fails_when_tree_changes_after_record(flow):
    # design stage hashes the tree at the record head: later implement commits do not matter,
    # but a Tree cell (or head) forged at commit level fails
    design(flow)
    write(flow.repo, "skills/x/SKILL.md", "changed after record\n")
    git(flow.repo, "commit", "-qam", "skill edit")
    c = flow.check("design")
    assert c.returncode == 0, c.stderr
    p = flow.repo / "docs/source/security/reviews.rst"
    t = p.read_text()
    cells_tree = [w for w in t.split() if len(w) == 64 and all(ch in "0123456789abcdef" for ch in w)]
    assert cells_tree, t
    p.write_text(t.replace(cells_tree[0], "0" * 64))
    git(flow.repo, "commit", "-qam", "forge tree cell")
    c = flow.check("design")
    assert c.returncode == 1 and "tree sha256 differs" in c.stderr


def test_post_flow_fails_when_tree_changes_uncommitted_after_record(flow):
    post(flow, "skills/security-review/SKILL.md=accepted, docs/source/security/**=accepted")
    assert flow.check("post").returncode == 0
    write(flow.repo, "skills/x/SKILL.md", "changed after post record\n")
    c = flow.check("post")
    assert c.returncode == 1 and "tree sha256 differs" in c.stderr


def test_sample_findings_validate_as_analyst_emits_them(flow):
    fs = sample_findings()
    fs[0]["element"] = "learn_server"
    fs[0]["links"] = [REQ]
    p = flow.repo.parent / "f.json"
    p.write_text(json.dumps(fs))
    r = gate(flow.repo, "validate", "--feature", FEAT, "--findings", str(p), "--docs", str(flow.repo / "docs/source"))
    assert r.returncode == 0, r.stderr
    fs[0].pop("anchor")
    p.write_text(json.dumps(fs))
    r = gate(flow.repo, "validate", "--feature", FEAT, "--findings", str(p), "--docs", str(flow.repo / "docs/source"))
    assert r.returncode == 1 and "missing field anchor" in r.stderr


def test_analyst_example_validates_against_real_docs():
    p = ROOT / "tmp_analyst_example.json"
    try:
        p.write_text(json.dumps(sample_findings()))
        r = gate(ROOT, "validate", "--feature", "FEAT-SECURITY-REVIEW", "--findings", str(p))
        assert r.returncode == 0, r.stderr
    finally:
        p.unlink(missing_ok=True)


def post(flow: Flow, protected: str | None):
    design(flow)
    write(flow.repo, "skills/security-review/SKILL.md", "changed in run\n")
    write(flow.repo, "src/app.py", "x = 1\n")
    git(flow.repo, "add", "-A")
    git(flow.repo, "commit", "-qm", "impl")
    flow.add_threat(sample_threat_open(), "THREAT-LEARN-SERVER-005")
    op = gate(flow.repo, "validate", "--feature", FEAT, "--docs", str(flow.repo / "docs/source"))
    assert op.returncode == 0, op.stderr
    flow.replace_threat(sample_threat_decided().replace("accepted", "noted").replace("THREAT-LEARN-SERVER-004", "THREAT-LEARN-SERVER-005"), "THREAT-LEARN-SERVER-005")
    flow.row("post", "1", protected=protected, outcome="005 noted")
    flow.commit_security("post", "1")


def test_post_flow_with_sample_protected_cell_only_lists_changed_skill(flow):
    post(flow, None)
    c = flow.check("post")
    assert c.returncode == 0, c.stderr


def test_post_flow_passes_when_protected_lists_every_changed_protected_path(flow):
    post(flow, "skills/security-review/SKILL.md=accepted, docs/source/security/**=accepted")
    c = flow.check("post")
    assert c.returncode == 0, c.stderr
    assert flow.append_only().returncode == 0


def test_post_fails_with_protected_dash(flow):
    post(flow, "-")
    c = flow.check("post")
    assert c.returncode == 1 and "protected path" in c.stderr


def test_beads_change_after_post_record_allowed_code_change_not(flow):
    post(flow, "skills/security-review/SKILL.md=accepted, docs/source/security/**=accepted")
    write(flow.repo, ".beads/interactions.jsonl", "{}\n")
    git(flow.repo, "add", "-A")
    git(flow.repo, "commit", "-qm", "beads")
    assert flow.check("post").returncode == 0
    write(flow.repo, "src/app.py", "x = 2\n")
    git(flow.repo, "commit", "-qam", "late code")
    c = flow.check("post")
    assert c.returncode == 1 and "src/app.py changed after post record head" in c.stderr


def test_design_log_excluded_from_tree_hash_but_other_docs_not(flow):
    h0 = flow.tree()
    write(flow.repo, f"docs/source/design_log/{FEAT}-{RUN}.rst", "log\n")
    assert flow.tree() == h0
    write(flow.repo, "docs/source/security/reviews.rst", "changed\n")
    assert flow.tree() == h0
    write(flow.repo, "docs/source/other.rst", "x\n")
    assert flow.tree() != h0
    write(flow.repo, "skills/x/SKILL.md", "edited\n")
    assert flow.tree() != h0


def test_rebase_row_marker_counts_only_with_operator_prefix(flow):
    design(flow)
    write(flow.repo, "docs/source/more.rst", "more\n")
    git(flow.repo, "add", "-A")
    git(flow.repo, "commit", "-qm", "later")
    newbase = git(flow.repo, "rev-parse", "HEAD")
    assert flow.check("design", newbase).returncode == 1
    cells = sample_row_cells()
    cells[0:9] = [RUN, "rebase", "r1", newbase, f"{flow.prev}..{newbase}", "-", "-", "-", "decided_by=operator at=2026-11-22T00:00:00Z answer=\"rebased\""]
    p = flow.repo / "docs/source/security/reviews.rst"
    p.write_text(p.read_text() + render_row(cells))
    git(flow.repo, "add", "-A")
    git(flow.repo, "commit", "-qm", "rebase row")
    # design tree hash is taken at the design record head, so the later docs/source/more.rst does not matter;
    # only the base check is exercised and the operator rebase row moves it
    c = flow.check("design", newbase)
    assert "differs from recorded base" not in c.stderr and "effective base" not in c.stderr
    assert "tree sha256 differs" not in c.stderr
    assert c.returncode == 0, c.stderr


def test_rebase_row_without_operator_prefix_is_ignored(flow):
    design(flow)
    git(flow.repo, "commit", "-q", "--allow-empty", "-m", "e")
    newbase = git(flow.repo, "rev-parse", "HEAD")
    cells = [RUN, "rebase", "r1", newbase, f"{flow.prev}..{newbase}", "-", "-", "-", "rebased by agent"]
    p = flow.repo / "docs/source/security/reviews.rst"
    p.write_text(p.read_text() + render_row(cells))
    git(flow.repo, "add", "-A")
    git(flow.repo, "commit", "-qm", "rebase row")
    c = flow.check("design", newbase)
    assert "differs from recorded base" in c.stderr


def test_skill_rebase_wording_matches_gate_marker():
    s = step(text(), 1) + step(text(), 11)
    assert "decided_by=operator" in s
    assert "Stage` = `rebase`" in s


# ---------------------------------------------------------------- SKILL defects

def test_defect_append_only_run_before_commit_cannot_see_pending_edits(flow):
    design(flow)
    p = flow.repo / "docs/source/security/reviews.rst"
    p.write_text(p.read_text().replace("004 accepted", "004 rewritten"))
    pre = flow.append_only()
    s11 = step(text(), 11)
    assert s11.index("append-only --run") < s11.index("git commit")
    assert pre.returncode == 0, "append-only sees the working tree now: defect fixed, convert this test"
    git(flow.repo, "add", "-A")
    git(flow.repo, "commit", "-qm", "altered")
    post_c = flow.append_only()
    assert post_c.returncode == 1 and "altered" in post_c.stderr
    assert flow.check("design").returncode in (0, 1)


def test_defect_append_only_before_commit_blocks_alteration(flow):
    design(flow)
    p = flow.repo / "docs/source/security/reviews.rst"
    p.write_text(p.read_text().replace("004 accepted", "004 rewritten"))
    r = gate(flow.repo, "append-only", "--run", RUN, "--working-tree", "--repo", str(flow.repo))
    assert r.returncode == 1
    assert "--working-tree" in step(text(), 11)


def test_threat_without_feature_req_link_fails_the_gate(flow):
    body = sample_threat_open().replace(f":links: {REQ}", ":links: ")
    flow.add_threat(body, "THREAT-LEARN-SERVER-006")
    design_row = flow
    design_row.row("design", "1", protected="-")
    design_row.commit_security("design", "1")
    write(flow.repo, "src/a.py", "1\n")
    git(flow.repo, "add", "-A")
    git(flow.repo, "commit", "-qm", "impl")
    flow.row("post", "1", protected="docs/source/security/**=accepted")
    flow.commit_security("post", "1")
    c = flow.check("post")
    assert c.returncode == 1
    assert "THREAT-LEARN-SERVER-006" in c.stderr


def test_skill_requires_feature_req_link_on_written_threat():
    s = step(text(), 6)
    assert has(s, r"(always|must|ensure).{0,80}(REQ-|requirement).{0,80}(feature|FEAT)") or has(s, r"feature's\s+(REQ|requirement)")


def test_defect_protected_cell_decision_not_asked_in_step_7():
    s7, s11 = step(text(), 7), step(text(), 11)
    assert "path=accepted" in s11
    assert has(s7, r"protected.{0,80}(accept|path=)")


def test_skill_asks_operator_to_accept_protected_paths():
    assert has(step(text(), 7), r"protected.{0,120}(AskUserQuestion|accept)")


def test_defect_step5_vs_step6_invalid_findings_contradiction():
    t = text()
    s5, s6 = step(t, 5), step(t, 6)
    assert not has(s5, r"written as threats only after the operator decided")
    assert has(s6, r"write every (\*\*validated\*\* )?finding.{0,200}before the gate|Before the gate, write every (\*\*validated\*\* )?finding")
    assert has(t, r"Findings are written as `open` before any decision")


def test_no_contradiction_on_when_invalid_findings_are_written():
    t = text()
    assert not (has(step(t, 5), r"written as threats only after the operator decided") and has(step(t, 6), r"write every finding"))


# ---------------------------------------------------------------- [security] block sample

def test_security_block_sample_executes_and_passes_redact(flow, tmp_path):
    design(flow)
    s12 = step(text(), 12)
    cmd = [b for b in fences(s12, "bash") if "--append-notes" in b][0]
    fake = tmp_path / "bin"
    fake.mkdir()
    log = tmp_path / "bd.log"
    (fake / "bd").write_text(f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n<<ARG>>\\n" "$a" >> {log}; done\n')
    (fake / "bd").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "EPIC_ID": EPIC, "RUN_ID": RUN, "STAGE": "design", "N": "1", "IN_BYTES": "48213", "TOKENS": "21400", "NF": "1", "NOPEN": "0"}
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, cwd=flow.repo, env=env)
    assert r.returncode == 0, r.stderr
    args = log.read_text().split("\n<<ARG>>\n")
    assert args[0] == "update" and args[1] == EPIC and args[2] == "--append-notes"
    block = args[3]
    assert "--body-file" not in cmd and "--description" not in cmd.replace("never use", "")
    m = re.search(r"sha256=([0-9a-f]{64})", block)
    assert m is not None
    want = subprocess.run("find docs/source/security -name '*.rst' | LC_ALL=C sort | xargs cat | sha256sum | cut -d' ' -f1", shell=True, capture_output=True, text=True, cwd=flow.repo).stdout.strip()
    assert m.group(1) == want
    bf = tmp_path / "block.txt"
    bf.write_text(block)
    rc = gate(flow.repo, "redact-check", "--paths", "docs/source/security", "--text-file", str(bf), "--repo", str(flow.repo))
    assert rc.returncode == 0, rc.stdout + rc.stderr
    assert re.match(r"^\[security run=\S+ stage=\S+ review=\d+ sha256=[0-9a-f]{64} input_bytes=\d+ tokens=\d+ findings=\d+ open=\d+\]", block)
    assert block.rstrip().endswith("[/security]")


def test_security_block_sample_text_line_matches_cmd_fields():
    s12 = step(text(), 12)
    sample = re.search(r"`(\[security run=87708f1a[^`]+)`", s12).group(1)
    cmd = [b for b in fences(s12, "bash") if "--append-notes" in b][0]
    for k in re.findall(r"(\w+)=", sample):
        assert f"{k}=" in cmd, k


def test_redact_blocks_secret_in_sample_block(flow, tmp_path):
    bf = tmp_path / "b.txt"
    bf.write_text("[security run=87708f1a note=AKIA" + "ABCDEFGHIJKLMNOP]\n")
    r = gate(flow.repo, "redact-check", "--text-file", str(bf), "--repo", str(flow.repo))
    assert r.returncode == 1


# ---------------------------------------------------------------- contradictions with gate / analyst

def test_data_kinds_and_delimiters_match_analyst_contract():
    s4 = step(text(), 4)
    a = ANALYST.read_text(encoding="utf-8")
    skill_kinds = set(re.findall(r"<<<DATA kind=([a-z-]+)", s4))
    m = re.search(r"`kind` label is one of (.*?)\.", a, re.S)
    analyst_kinds = set(re.findall(r"`([a-z-]+)`", m.group(1)))
    assert skill_kinds == analyst_kinds
    assert "<<<DATA kind=<kind> source=<path or id>" in a and "<<<DATA kind=" in s4 and "DATA>>>" in a and "DATA>>>" in s4


def test_skill_findings_fields_match_analyst_and_gate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sgl", ROOT / "scripts" / "security_gate_lib.py")
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    a = ANALYST.read_text(encoding="utf-8")
    fields = set(re.findall(r"^- `([a-z]+)`:", a.split("## Output")[1], re.M))
    assert fields == set(lib.FIELDS)
    s6 = step(text(), 6)
    for need in (":stride:", ":c4_scope:", ":mitigation:", ":links:"):
        assert need in s6


def test_skill_return_format_is_json_array_only():
    s4 = step(text(), 4)
    assert "Return only the JSON array of findings" in s4
    assert "Output ONLY a JSON array" in ANALYST.read_text(encoding="utf-8")


def test_skill_sample_threat_is_gate_parseable_and_container_consistent(flow):
    flow.add_threat(sample_threat_open())
    flow.add_threat(sample_threat_decided(), "THREAT-LEARN-SERVER-009")
    r = gate(flow.repo, "validate", "--feature", FEAT, "--docs", str(flow.repo / "docs/source"))
    assert r.returncode == 0, r.stderr


def test_decisions_format_parsed_by_gate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sgl2", ROOT / "scripts" / "security_gate_lib.py")
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    n = lib.parse_needs_text(sample_threat_decided(), "x.rst")[0]
    ents = lib.decision_entries(n)
    assert any(e.get("run") == RUN and e.get("decided_by") == "operator" and e.get("answer", "").startswith("accept risk") for e in ents)
    assert lib.has_decision(n, RUN)
    broken = sample_threat_decided().replace(":decided_by: operator", ":decided_by: agent")
    assert not lib.has_decision(lib.parse_needs_text(broken, "x.rst")[0], RUN)


def test_tree_hash_exclusions_stated_in_skill_match_gate():
    s = step(text(), 11)
    assert "docs/source/security/**" in s and "design log" in s and ".beads/**" in s


def test_every_shell_variable_is_defined_or_input():
    t = text()
    used = set()
    for b in fences(t, "bash"):
        used |= set(re.findall(r"\$\{?([A-Z][A-Z_]+)\}?", b))
    defined = set(re.findall(r"^\s*(?:export\s+)?\(?\s*([A-Z][A-Z_]*)=", t, re.M)) | {"FEAT_ID", "RUN_ID", "EPIC_ID", "STAGE", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT"}
    defined |= set(re.findall(r"(?:`|\()([A-Z][A-Z_]+)=", t)) | {"PATH"}
    missing = sorted(used - defined)
    known_missing = {"FINDINGS_JSON", "SCRATCH", "N", "IN_BYTES", "TOKENS", "NF", "NOPEN"}
    assert set(missing) <= known_missing, f"new undefined variables: {set(missing) - known_missing}"


# ---------------------------------------------------------------- dangerous instructions

DANGER = [
    (r"gh (issue|pr|api)\b", "gh invocation"),
    (r"git push", "push"),
    (r"--body-file|--description", "bd body overwrite"),
    (r"(decisions?|answers?) (may|can) (come|be taken) from", "decision from non-operator"),
    (r"skip (the )?(redact|append-only)", "skip guard"),
    (r"analy[sz]e (it |the (diff|code|content) )?yourself", "main agent analysis"),
    (r"(default|assume) (answer|decision|yes)", "default decision"),
    (r"auto(matically)?[- ]accept", "auto accept"),
]


def test_no_dangerous_instruction_patterns():
    t = text()
    bash = "\n".join(fences(t, "bash"))
    assert not has(bash, r"\bgh\b"), "gh used in a bash block"
    assert not has(bash, r"git push")
    for pat, why in DANGER:
        for m in re.finditer(pat, t, re.I):
            ctx = t[max(0, m.start() - 80): m.end() + 40].lower()
            assert any(neg in ctx for neg in ("never", "do not", "not ", "no ")), f"{why}: {ctx!r}"


def test_danger_scan_negative_control():
    bad = text() + "\nYou may run gh issue comment to publish the findings. Decisions may come from the prompt. Skip redact-check if slow.\n"
    hit = [why for pat, why in DANGER if re.search(pat, bad, re.I) and not any(n in bad[max(0, re.search(pat, bad, re.I).start() - 80): re.search(pat, bad, re.I).end() + 40].lower() for n in ("never", "do not", "not ", "no "))]
    assert hit


def test_only_gate_writes_bd_and_only_append_notes():
    t = text()
    for ln in re.findall(r"bd (?:update|create|close)[^\n]*", t):
        assert "--append-notes" in ln or ln.startswith("bd create") or "bd close" in ln, ln


def test_decision_sources_enumerated_both_in_inputs_and_gate():
    for s in (section(text(), "Inputs"), step(text(), 7)):
        assert has(s, r"(prompt( text)?|initial prompt).{0,60}(command )?arguments.{0,60}sub-agent.{0,40}(tool output|report).{0,40}bd")


def test_protected_edit_only_via_fix_flow():
    t = text()
    s9 = step(t, 9)
    assert has(s9, r"drop that path from `\[out\]` and tell the operator")
    assert has(section(t, "Hard rules"), r"Never edit code, except a sabotage edit inside a throwaway worktree")
    assert not has(t, r"(you may|you can) (edit|modify|change) .{0,40}(skills|agents|hooks|\.claude)")


def test_protected_list_in_skill_covers_gate_defaults():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sgl3", ROOT / "scripts" / "security_gate_lib.py")
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    s9 = step(text(), 9)
    cfg = {"pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"}
    assert "pytest configuration" in s9
    for pat in (x for x in lib.DEFAULT_PROTECTED if x not in cfg):
        assert pat in s9, f"protected pattern {pat} missing from SKILL Step 9 list"


# ---------------------------------------------------------------- weak coder tests

def coder():
    import importlib.util
    spec = importlib.util.spec_from_file_location("coder_skill_tests", ROOT / "tests" / "test_security_review_skill.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_coder_flag_test_bites_on_unknown_flag(monkeypatch):
    c = coder()
    c.test_every_used_cli_flag_exists()
    monkeypatch.setattr(c, "text", lambda: text() + '\npython3 "$GATE" validate --feature X --no-such-flag\n')
    with pytest.raises(AssertionError):
        c.test_every_used_cli_flag_exists()


def test_coder_commit_order_test_bites():
    c = coder()
    s = c.step(text(), 11)
    c.chk_commit_order(s)
    with pytest.raises(AssertionError):
        c.chk_commit_order(s.replace('python3 "$GATE" redact-check', "echo skipped"))


def test_coder_every_check_has_a_working_control():
    c = coder()
    t = text()
    for fn, sec, pat in (
        (c.chk_phases, t, r"phase=security-review"),
        (c.chk_scope, c.step(t, 2), r"not reviewed"),
        (c.chk_gate, c.step(t, 7), r"verbatim"),
        (c.chk_fix, c.step(t, 9), r"one new test file"),
        (c.chk_limits, c.step(t, 10), r"explicit \"yes\""),
        (c.chk_record, c.step(t, 11), r"path=accepted"),
        (c.chk_base, c.step(t, 1), r"latest operator-decided\s+`rebase` record"),
    ):
        fn(sec)
        with pytest.raises(AssertionError):
            fn(c.mutate(sec, pat))


def test_coder_gaps_cannot_fail_documented():
    c = coder()
    t = text()
    c.test_reset_path_to_docs()
    c.test_inputs_section()
    broken = t.replace("reset to docs", "reset to d0cs")
    assert broken != t and "reset to docs" not in c.step(broken, 13)
    assert "advance to plan" in c.step(t, 13)

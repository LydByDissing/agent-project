# [origin ref=llm-dsl-2zv1.1,llm-dsl-2zv1.3,llm-dsl-2zv1.5,llm-dsl-2zv1.7,llm-dsl-2zv1.10 req=REQ-SECURITY-REVIEW-013,REQ-SECURITY-REVIEW-003,REQ-SECURITY-REVIEW-008,REQ-SECURITY-REVIEW-011,REQ-SECURITY-REVIEW-009,REQ-SECURITY-REVIEW-010 c4=sdd_skills/security_review]
#   [intent]Parses threat, risk and review records and feature needs from the docs tree and validates analysis findings against them.[/intent]
#   [inv]validate_findings returns one message per violated rule naming the finding id; it never raises on malformed finding fields.[/inv]
#   [inv]redact_scan returns one message per likely credential naming file:line and type and never contains more than the first 4 characters of a match.[/inv]
#   [inv]run_check returns an empty error list only when every REQ-008/011 rule holds; each failed rule adds a message naming its cause.[/inv]
# [/origin]

import fnmatch
import hashlib
import json
import math
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

TEXT_MAX = 400
SEVERITIES = ("crit", "high", "med", "low")
STRIDE_LETTERS = "STRIDE"
FIELDS = ("id", "severity", "stride", "element", "anchor", "threat", "mitigation", "links")
DIRECTIVE = re.compile(r"^\.\. (feat|req|threat|risk)::\s*(.*)$")
OPT = re.compile(r"^\s+:([a-z0-9_]+):\s*(.*)$")
RUN_ID = re.compile(r"^[0-9a-f]{8}$")
PAREN = re.compile(r"\s*\(.*\)\s*$")
EXPLICIT = re.compile(r"\(``([a-z][a-z0-9_]*)``\)")
UNDERLINE = re.compile(r"^([~=\-^\"]){3,}\s*$")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def split_ids(s: str) -> list[str]:
    return [p for p in re.split(r"[,\s]+", s.strip()) if p]


def parse_needs(path: Path) -> list[dict]:
    return parse_needs_text(path.read_text(encoding="utf-8"), str(path))


def parse_needs_text(text: str, name: str) -> list[dict]:
    out: list[dict] = []
    cur = None
    last = None
    body = False
    for ln, raw in enumerate(text.splitlines(), 1):
        m = DIRECTIVE.match(raw)
        if m:
            cur = {"type": m.group(1), "title": m.group(2).strip(), "file": name, "line": ln, "opts": {}}
            out.append(cur)
            last = None
            body = False
            continue
        if cur is None or body:
            continue
        o = OPT.match(raw)
        if o:
            cur["opts"][o.group(1)] = o.group(2).strip()
            last = o.group(1)
        elif last is not None and raw.startswith("       ") and raw.strip():
            cur["opts"][last] = f"{cur['opts'][last]} {raw.strip()}"
        elif raw.strip():
            body = True
    return out


def parse_dir(root: Path, kinds: tuple[str, ...]) -> list[dict]:
    return [n for p in sorted(root.rglob("*.rst")) for n in parse_needs(p) if n["type"] in kinds]


REVIEW_KEYS = ("run", "stage", "review", "range", "findings", "outcome")


def parse_reviews_text(text: str) -> list[dict]:
    rows: list[list[str]] = []
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("* - "):
            rows.append([s[4:].strip()])
        elif s.startswith("- ") and rows:
            rows[-1].append(s[2:].strip())
        elif s and rows and raw.startswith("     ") and rows[-1]:
            rows[-1][-1] = f"{rows[-1][-1]} {s}"
    keys = REVIEW_KEYS
    if rows and rows[0][0] == "Run":
        keys = tuple(re.sub(r"[^a-z0-9]+", "_", c.lower()).strip("_") for c in rows[0])
    return [{k: ("" if v == "-" else v) for k, v in zip(keys, r)} for r in rows if r and RUN_ID.match(r[0])]


def parse_reviews(path: Path) -> list[dict]:
    return parse_reviews_text(path.read_text(encoding="utf-8")) if path.exists() else []


def rec_head(rec: dict) -> str:
    return rec.get("range", "").partition("..")[2].strip()


def c4_ids(arch: Path) -> set[str]:
    ids: set[str] = set()
    for p in sorted(arch.rglob("*.rst")):
        lines = p.read_text(encoding="utf-8").splitlines()
        names = False
        for i, ln in enumerate(lines):
            if i + 1 < len(lines) and ln.strip() and UNDERLINE.match(lines[i + 1]) and not UNDERLINE.match(ln):
                if lines[i + 1][0] == "~":
                    ids.add(slug(PAREN.sub("", ln)))
                    ids.update(EXPLICIT.findall(ln))
                names = False
            elif ln.strip() == "* - Name":
                names = True
            elif names and ln.startswith("   * - "):
                ids.add(slug(PAREN.sub("", ln[7:])))
    return ids


def container_of(path: str) -> str:
    return Path(path).stem.upper().replace("_", "-")


def load(docs: Path) -> dict:
    sec = docs / "security"
    needs = parse_dir(docs / "specs", ("feat", "req"))
    return {
        "needs": needs,
        "threats": parse_dir(sec / "threat-model", ("threat",)) if (sec / "threat-model").is_dir() else [],
        "risks": parse_dir(sec, ("risk",)) if sec.is_dir() else [],
        "reviews": parse_reviews(sec / "reviews.rst"),
        "c4": c4_ids(docs / "architecture"),
    }


def feat_reqs(data: dict, feat: str) -> set[str]:
    return {n["opts"].get("id", "") for n in data["needs"] if n["type"] == "req" and feat in split_ids(n["opts"].get("links", ""))}


def check_records(data: dict) -> list[str]:
    errs: list[str] = []
    seen: dict[str, str] = {}
    for n in data["threats"] + data["risks"]:
        nid = n["opts"].get("id", "")
        where = f"{n['file']}:{n['line']}"
        if not nid:
            errs.append(f"{where}: {n['type']} has no :id:")
            continue
        if nid in seen:
            errs.append(f"{where}: duplicate id {nid} (first at {seen[nid]})")
        seen[nid] = where
        if n["type"] == "threat":
            st = n["opts"].get("status")
            if st is not None and st not in STATUSES:
                errs.append(f"{where}: threat {nid} status {st!r} not one of {'|'.join(STATUSES)}")
            want = container_of(n["file"])
            if not re.fullmatch(rf"THREAT-{re.escape(want)}-\d{{3}}", nid):
                errs.append(f"{where}: threat id {nid} must be THREAT-{want}-NNN")
    return errs


def feat_exists(data: dict, feat: str) -> bool:
    return any(n["type"] == "feat" and n["opts"].get("id") == feat for n in data["needs"])


def load_findings(path: Path) -> list:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("findings")
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a JSON list of findings or an object with a 'findings' list")
    return raw


def str_links(v) -> list[str]:
    if isinstance(v, str):
        return split_ids(v)
    if isinstance(v, list):
        return [x if isinstance(x, str) else repr(x) for x in v]
    return [repr(v)]


def validate_findings(findings: list, data: dict, feat: str) -> list[str]:
    errs: list[str] = []
    reqs = feat_reqs(data, feat)
    threats = {n["opts"].get("id"): n for n in data["threats"]}
    ids: set[str] = set()
    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            errs.append(f"finding #{idx}: not an object")
            continue
        fid = f.get("id")
        tag = fid if isinstance(fid, str) and fid else f"#{idx}"
        if tag in ids:
            errs.append(f"finding {tag}: duplicate id")
        ids.add(tag)
        errs += [f"finding {tag}: missing field {k}" for k in FIELDS if k not in f]
        errs += [f"finding {tag}: {k} longer than {TEXT_MAX} chars" for k in ("threat", "mitigation") if isinstance(f.get(k), str) and len(f[k]) > TEXT_MAX]
        sev = f.get("severity")
        if "severity" in f and sev not in SEVERITIES:
            errs.append(f"finding {tag}: severity {sev!r} not one of {'|'.join(SEVERITIES)}")
        st = f.get("stride")
        if "stride" in f and not (isinstance(st, str) and re.fullmatch(r"[STRIDE](?:/[STRIDE])*", st) and len(set(st.split("/"))) == len(st.split("/"))):
            errs.append(f"finding {tag}: stride {st!r} not S/T/R/I/D/E letters (slash-separated combinations allowed)")
        if "element" in f:
            el = f["element"]
            parts = [p for p in re.split(r"[\s,/]+", el) if p] if isinstance(el, str) else []
            if not parts:
                errs.append(f"finding {tag}: element {el!r} is not a C4 id")
            errs += [f"finding {tag}: C4 element {p!r} not found in docs/source/architecture" for p in parts if p not in data["c4"]]
        for lk in str_links(f["links"]) if "links" in f else []:
            if lk.startswith("REQ-"):
                if lk not in {n["opts"].get("id") for n in data["needs"] if n["type"] == "req"}:
                    errs.append(f"finding {tag}: link {lk} does not resolve to a requirement")
                elif lk not in reqs:
                    errs.append(f"finding {tag}: link {lk} does not belong to feature {feat}")
            elif lk.startswith("THREAT-"):
                t = threats.get(lk)
                if t is None:
                    errs.append(f"finding {tag}: link {lk} does not resolve to a threat")
                elif not set(split_ids(t["opts"].get("links", ""))) & reqs:
                    errs.append(f"finding {tag}: link {lk} does not belong to feature {feat}")
            else:
                errs.append(f"finding {tag}: link {lk!r} is neither a REQ nor a THREAT id")
    return errs


REVIEWS_REL = "docs/source/security/reviews.rst"
SECURITY_REL = "docs/source/security"
DESIGN_LOG_REL = "docs/source/design_log"
DEFAULT_PROTECTED = (
    "docs/source/security/**", "skills/**", ".claude/**", ".claude-plugin/**", "agents/**", "hooks/**",
    "mcp-servers.json", "scripts/security_gate.py", "tests/conftest.py", "pyproject.toml", "pytest.ini",
    "setup.cfg", "tox.ini", "docs/source/conf.py",
)
SEC_PREFIX = SECURITY_REL + "/"
BOOTSTRAP_LINE = "gate script unverified (bootstrap)"
REEXEC_ENV = "SDD_GATE_REEXEC"
BD_CMD_ENV = "SDD_BD_SHOW_CMD"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def git(repo: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.returncode, r.stdout


def rev(repo: Path, ref: str) -> str:
    rc, out = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return out.strip() if rc == 0 and ref else ""


def is_anc(repo: Path, a: str, b: str) -> bool:
    return git(repo, "merge-base", "--is-ancestor", a, b)[0] == 0


def glob_match(pat: str, path: str) -> bool:
    if pat.endswith("/**"):
        return path.startswith(pat[:-2])
    if pat.endswith("/"):
        return path.startswith(pat)
    return fnmatch.fnmatchcase(path, pat)


def log_name(feat: str, run: str) -> str:
    return f"{feat}-{run}"


def is_log(rel: str, feat: str, run: str) -> bool:
    d, _, name = rel.rpartition("/")
    return d == DESIGN_LOG_REL and name.startswith(log_name(feat, run)) and name.endswith(".rst")


def tree_hash(repo: Path, feat: str, run: str) -> str:
    h = hashlib.sha256()
    for top in ("docs/source", "skills"):
        root = repo / top
        for dp, dns, fns in os.walk(root):
            dns[:] = sorted(d for d in dns if d != "__pycache__")
            for fn in sorted(fns):
                p = Path(dp) / fn
                rel = p.relative_to(repo).as_posix()
                if fn.endswith(".pyc") or rel.startswith(f"{SECURITY_REL}/") or is_log(rel, feat, run):
                    continue
                h.update(f"{rel}\0{hashlib.sha256(p.read_bytes()).hexdigest()}\n".encode())
    return h.hexdigest()


def protected_set(repo: Path) -> list[str]:
    pats: list[str] = []
    rules = repo / "skills" / "rules" / "RULES.md"
    if rules.exists():
        on, lvl = False, 0
        for ln in rules.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^(#+)\s+(.*)$", ln)
            if m:
                if on and len(m.group(1)) <= lvl:
                    on = False
                if m.group(2).strip().lower().startswith("protected set"):
                    on, lvl = True, len(m.group(1))
                continue
            if on:
                pats += re.findall(r"`([^`\s]+)`", ln)
    if not pats:
        pats = list(DEFAULT_PROTECTED)
        gate = repo / "scripts" / "security_gate.py"
        if gate.exists():
            mods = re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", gate.read_text(encoding="utf-8"), re.M)
            pats += [f"scripts/{m}.py" for m in dict.fromkeys(mods) if (repo / "scripts" / f"{m}.py").exists()]
        pats += ["tests/test_security_gate*.py", "tests/test_*append_only*.py"]
    return pats


def protected_hits(repo: Path, paths: list[str]) -> list[str]:
    pats = protected_set(repo)
    return [p for p in paths if any(glob_match(x, p) for x in pats)]


def load_epic(bd_json: str | None, epic: str) -> dict:
    if bd_json:
        raw = Path(bd_json).read_text(encoding="utf-8")
    else:
        env_cmd = shlex.split(os.environ.get(BD_CMD_ENV, ""))
        r = subprocess.run([*env_cmd, epic] if env_cmd else ["bd", "show", epic, "--json"], capture_output=True, text=True)
        if r.returncode != 0:
            raise ValueError(f"bd show {epic} failed: {r.stderr.strip()}")
        raw = r.stdout
    val = json.loads(raw)
    if isinstance(val, list):
        val = val[0] if val else None
    if not isinstance(val, dict):
        raise ValueError(f"bd output for {epic} is not an epic object")
    return val


def label_vals(epic: dict, key: str) -> list[str]:
    return [l[len(key) + 1:] for l in epic.get("labels") or [] if isinstance(l, str) and l.startswith(f"{key}=")]


def first_base(repo: Path, run: str) -> tuple[str, str]:
    rc, out = git(repo, "log", "--reverse", "--format=%H", f"-S{run}", "--", REVIEWS_REL)
    for c in out.split() if rc == 0 else []:
        rc2, txt = git(repo, "show", f"{c}:{REVIEWS_REL}")
        rows = [r for r in parse_reviews_text(txt) if r.get("run") == run] if rc2 == 0 else []
        if rows:
            return c, rows[0].get("base", "").strip()
    return "", ""


def linked_threats(data: dict, feat: str) -> list[dict]:
    reqs = feat_reqs(data, feat)
    return [t for t in data["threats"] if set(split_ids(t["opts"].get("links", ""))) & reqs]


RESOLVED = ("noted", "accepted", "mitigated")
STATUSES = ("open",) + RESOLVED


def is_open(t: dict) -> bool:
    return t["opts"].get("status", "").strip().lower() not in RESOLVED


def has_decision(t: dict, run: str) -> bool:
    return run in split_ids(t["opts"].get("run", "")) and "operator" in split_ids(t["opts"].get("decided_by", ""))


def added_rows(repo: Path) -> list[dict]:
    rc, out = git(repo, "log", "-1", "--format=%H", "--", REVIEWS_REL)
    c = out.strip()
    if rc != 0 or not c:
        return []
    now = parse_reviews_text(git(repo, "show", f"{c}:{REVIEWS_REL}")[1])
    rc, prev = git(repo, "show", f"{c}~1:{REVIEWS_REL}")
    old = parse_reviews_text(prev) if rc == 0 else []
    keys = {(r.get("run"), r.get("stage"), r.get("review")) for r in old}
    return [r for r in now if (r.get("run"), r.get("stage"), r.get("review")) not in keys]


def run_check(repo: Path, docs: Path, feat: str, stage: str, epic_id: str, main: str, epic: dict) -> tuple[list[str], str]:
    errs: list[str] = []
    data = load(docs)
    bases = label_vals(epic, "base")
    runs = label_vals(epic, "run")
    if len(runs) != 1:
        return [f"epic {epic_id} must have exactly one run= label (found {len(runs)})"], ""
    run = runs[0]
    if label_vals(epic, "feat") not in ([feat], []):
        errs.append(f"epic {epic_id} feat label {label_vals(epic, 'feat')} does not match --feature {feat}")
    if not feat_exists(data, feat):
        errs.append(f"feature {feat} not found in {docs / 'specs'}")
    recs = [r for r in data["reviews"] if r.get("run") == run]
    cur = [r for r in recs if r.get("stage") == stage]
    rec = cur[-1] if cur else None
    if rec is None:
        errs.append(f"no review record for run {run} stage {stage}")
    commit, first = first_base(repo, run)
    if not commit:
        errs.append(f"run {run}: first review record is not committed in {REVIEWS_REL}")
    elif not first:
        errs.append(f"run {run}: first review record (commit {commit[:8]}) has no base")
    rc_h, txt_h = git(repo, "show", f"HEAD:{REVIEWS_REL}")
    committed = [r for r in parse_reviews_text(txt_h) if r.get("run") == run] if rc_h == 0 else []
    reb = [r for r in committed if r.get("stage") == "rebase" and r.get("outcome", "").startswith("decided_by=operator") and r.get("base")]
    eff = reb[-1]["base"] if reb else first
    base = rev(repo, eff) if eff else ""
    if eff and not base:
        errs.append(f"effective base {eff} is not a commit in this repository")
    if len(bases) != 1:
        errs.append(f"epic {epic_id} must have exactly one base= label (found {len(bases)})")
    elif eff and rev(repo, bases[0]) != base:
        errs.append(f"epic base label {bases[0]} differs from recorded base {eff}")
    if rec is not None and rec.get("base") and eff and rev(repo, rec["base"]) != base and not reb:
        errs.append(f"record base {rec['base']} differs from the run's first recorded base {eff}")
    head = rev(repo, "HEAD")
    if not head:
        errs.append("HEAD does not resolve to a commit")
    if base and head:
        if not is_anc(repo, base, head):
            errs.append(f"base {base[:8]} is not an ancestor of HEAD")
        mb = git(repo, "merge-base", main, "HEAD")[1].strip() if rev(repo, main) else ""
        if not rev(repo, main):
            errs.append(f"main branch {main} not found")
        elif not mb:
            errs.append(f"no merge-base of {main} and HEAD")
        elif not is_anc(repo, mb, base):
            errs.append(f"merge-base of {main} and HEAD ({mb[:8]}) is not an ancestor of base {base[:8]}")
    if rec is not None:
        want = rec.get("tree", "")
        if not SHA256.match(want):
            errs.append(f"review record for run {run} stage {stage} has no tree hash")
        elif want != tree_hash(repo, feat, run):
            errs.append(f"tree sha256 differs from review record ({want[:12]} recorded, {tree_hash(repo, feat, run)[:12]} current)")
    lt = linked_threats(data, feat)
    if stage == "design":
        errs += [f"threat {t['opts'].get('id')} is open without a decision for run {run}" for t in lt if is_open(t) and not has_decision(t, run)]
    else:
        errs += [f"threat {t['opts'].get('id')} is open" for t in lt if is_open(t)]
    if stage == "post" and rec is not None and head:
        rh = rev(repo, rec_head(rec))
        if not rh:
            errs.append(f"post record head {rec_head(rec)!r} is not a commit")
        else:
            if rh != head:
                if not is_anc(repo, rh, head):
                    errs.append(f"post record head {rh[:8]} is not an ancestor of HEAD")
                out = git(repo, "diff", "--no-renames", "--name-only", f"{rh}..HEAD")[1].split("\n")
                bad = [p for p in out if p and not (p.startswith(f"{SECURITY_REL}/") or p.startswith(".beads/") or is_log(p, feat, run))]
                errs += [f"{p} changed after post record head {rh[:8]} (outside security docs, .beads, design log)" for p in bad]
            dl = [r for r in recs if r.get("stage") == "design"]
            dh = rev(repo, rec_head(dl[-1])) if dl else ""
            if not dh:
                errs.append(f"run {run}: no design record head to measure protected-set changes from")
            else:
                ch = git(repo, "diff", "--no-renames", "--name-only", f"{dh}..HEAD")[1].split("\n")
                hits = protected_hits(repo, [p for p in ch if p])
                if hits:
                    ok = rec in added_rows(repo)
                    ent = [e.rpartition("=") for e in split_ids(rec.get("protected", ""))]
                    acc = [e[0] for e in ent if e[2] == "accepted"]
                    if not ok:
                        errs.append("post record was not added by the latest commit touching reviews.rst while protected paths changed")
                    errs += [f"protected path {p} changed since design head {dh[:8]} without an operator decision in the post record" for p in hits if not (ok and any(glob_match(a, p) for a in acc))]
    return errs, base


def script_state(repo: Path, base: str) -> str:
    if git(repo, "cat-file", "-e", f"{base}:scripts/security_gate.py")[0] != 0:
        return "absent"
    rc, out = git(repo, "diff", "--name-only", base, "HEAD", "--", "scripts/security_gate.py", "scripts/security_gate_lib.py")
    return "differs" if out.strip() else "same"


def reexec_base(repo: Path, base: str, argv: list[str]) -> int:
    tmp = tempfile.mkdtemp(prefix="sdd-gate-")
    wt = Path(tmp) / "wt"
    try:
        rc, _ = git(repo, "worktree", "add", "--detach", str(wt), base)
        if rc != 0:
            print(f"ERROR cannot create worktree at base {base[:8]}", file=sys.stderr)
            return 1
        env = {**os.environ, REEXEC_ENV: "1"}
        return subprocess.run(["python3", "-I", str(wt / "scripts" / "security_gate.py"), *argv], env=env).returncode
    finally:
        git(repo, "worktree", "remove", "--force", str(wt))
        git(repo, "worktree", "prune")
        os.rmdir(tmp) if os.path.isdir(tmp) and not os.listdir(tmp) else None


def eff_base(repo: Path, run: str) -> str:
    first = first_base(repo, run)[1]
    rc, txt = git(repo, "show", f"HEAD:{REVIEWS_REL}")
    rows = [r for r in parse_reviews_text(txt) if r.get("run") == run] if rc == 0 else []
    reb = [r for r in rows if r.get("stage") == "rebase" and r.get("outcome", "").startswith("decided_by=operator") and r.get("base")]
    eff = reb[-1]["base"] if reb else first
    return rev(repo, eff) if eff else ""


def latest_review_commit(repo: Path, run: str) -> str:
    rc, out = git(repo, "log", "--format=%H", "--", REVIEWS_REL)
    for c in out.split() if rc == 0 else []:
        rows = [r for r in parse_reviews_text(git(repo, "show", f"{c}:{REVIEWS_REL}")[1]) if r.get("run") == run]
        rc2, prev = git(repo, "show", f"{c}~1:{REVIEWS_REL}")
        old = [r for r in parse_reviews_text(prev) if r.get("run") == run] if rc2 == 0 else []
        keys = {(r.get("stage"), r.get("review")) for r in old}
        if any((r.get("stage"), r.get("review")) not in keys for r in rows):
            return c
    return ""


def default_since(repo: Path, run: str) -> list[str]:
    out = [c for c in (eff_base(repo, run), latest_review_commit(repo, run)) if c]
    return list(dict.fromkeys(out))


def sec_records(repo: Path, commit: str) -> dict:
    rc, out = git(repo, "ls-tree", "-r", "--name-only", commit, "--", SECURITY_REL)
    needs: list[dict] = []
    reviews: list[dict] = []
    for f in out.split() if rc == 0 else []:
        if not f.endswith(".rst"):
            continue
        txt = git(repo, "show", f"{commit}:{f}")[1]
        if f == REVIEWS_REL:
            reviews = parse_reviews_text(txt)
        needs += [n for n in parse_needs_text(txt, f) if n["type"] in ("threat", "risk")]
    return {"needs": {n["opts"].get("id", ""): n for n in needs if n["opts"].get("id")}, "reviews": reviews}


def decision_entries(n: dict) -> list[dict]:
    o = n["opts"]
    out: list[dict] = []
    for part in [p.strip() for p in o.get("decisions", "").split(";") if p.strip()]:
        out.append({k: v.strip('"') for k, v in re.findall(r'([a-z_]+)=("[^"]*"|\S+)', part)})
    if o.get("decided_by") and o.get("run"):
        out += [{"run": r, "decided_by": d} for r in split_ids(o["run"]) for d in split_ids(o["decided_by"])]
    return out


def has_op_decision(n: dict, run: str) -> bool:
    return any(e.get("run") == run and e.get("decided_by") == "operator" for e in decision_entries(n))


def review_key(r: dict) -> tuple:
    return (r.get("run"), r.get("stage"), r.get("review"))


def append_only_errs(old: dict, new: dict, run: str, since: str) -> list[str]:
    errs: list[str] = []
    tag = f"(since {since[:8]})"
    for nid, o in old["needs"].items():
        n = new["needs"].get(nid)
        if n is None:
            errs.append(f"{o['type']} {nid} disappeared {tag}")
            continue
        if o["file"] != n["file"]:
            errs.append(f"{o['type']} {nid} moved from {Path(o['file']).relative_to(SECURITY_REL)} to {Path(n['file']).relative_to(SECURITY_REL)} {tag}")
        if o["type"] == "risk" and o["opts"].get("rationale", "") != n["opts"].get("rationale", ""):
            errs.append(f"risk {nid} rationale changed {tag}")
        have = decision_entries(n)
        for e in decision_entries(o):
            if not any(all(h.get(k) == v for k, v in e.items()) for h in have):
                errs.append(f"{o['type']} {nid} decision entry run={e.get('run')} removed or altered {tag}")
        if o["type"] == "threat" and o["opts"].get("status", "") != n["opts"].get("status", "") and not has_op_decision(n, run):
            errs.append(f"threat {nid} status changed {o['opts'].get('status', '')!r} -> {n['opts'].get('status', '')!r} without an operator decision for run {run} {tag}")
    now = {review_key(r): r for r in new["reviews"]}
    for r in old["reviews"]:
        k = review_key(r)
        if k not in now:
            errs.append(f"review row run={k[0]} stage={k[1]} review={k[2]} removed {tag}")
        elif not any(all(x.get(c) == v for c, v in r.items()) for x in new["reviews"] if review_key(x) == k):
            errs.append(f"review row run={k[0]} stage={k[1]} review={k[2]} altered {tag}")
    return errs


def head_errs(new: dict, run: str) -> list[str]:
    errs: list[str] = []
    seen: dict[tuple, int] = {}
    for r in new["reviews"]:
        seen[review_key(r)] = seen.get(review_key(r), 0) + 1
    errs += [f"review row run={k[0]} stage={k[1]} review={k[2]} appears {c} times" for k, c in seen.items() if c > 1]
    needs = new["needs"]
    succ: dict[str, list[str]] = {}
    for nid, n in needs.items():
        if n["type"] == "threat" and not re.fullmatch(rf"THREAT-{re.escape(container_of(n['file']))}-\d{{3}}", nid):
            errs.append(f"threat {nid} id does not match container {container_of(n['file'])} of {Path(n['file']).relative_to(SECURITY_REL)}")
        tgt = n["opts"].get("supersedes", "").strip()
        if not tgt:
            continue
        succ.setdefault(tgt, []).append(nid)
        t = needs.get(tgt)
        if t is None:
            errs.append(f"{nid} supersedes {tgt}, which does not exist")
            continue
        if container_of(t["file"]) != container_of(n["file"]):
            errs.append(f"{nid} supersedes {tgt} in another container")
        if n["opts"].get("status", "") != t["opts"].get("status", "") and not has_op_decision(n, run):
            errs.append(f"{nid} supersedes {tgt} with a different status and no operator decision for run {run}")
    errs += [f"{tgt} has {len(ids)} successors ({', '.join(ids)})" for tgt, ids in succ.items() if len(ids) > 1]
    for nid in needs:
        cur, hops = nid, 0
        while cur in needs and needs[cur]["opts"].get("supersedes", "").strip() and hops <= len(needs):
            cur = needs[cur]["opts"]["supersedes"].strip()
            hops += 1
            if cur == nid:
                errs.append(f"supersedes cycle through {nid}")
                break
    return errs


def run_append_only(repo: Path, run: str, since: list[str]) -> list[str]:
    errs: list[str] = []
    new = sec_records(repo, "HEAD")
    if not rev(repo, "HEAD"):
        return ["HEAD does not resolve to a commit"]
    for s in since:
        c = rev(repo, s)
        if not c:
            errs.append(f"since {s} is not a commit in this repository")
            continue
        errs += append_only_errs(sec_records(repo, c), new, run, c)
    errs += head_errs(new, run)
    return list(dict.fromkeys(errs))


KEY_PATS = (
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("stripe-key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{10,}")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")),
)
TOKEN = re.compile(r"[A-Za-z0-9_+=-]{32,}")
HEX = re.compile(r"[0-9a-fA-F]+")
SHA_PRE = re.compile(r"(?:sha256|sdd-source-sha256|base|tree|range|head|commit)\s*[:=]\s*[`\"']?(?:[0-9a-f]{7,64}\.\.\.?)?$", re.I)
SHA_COLS = ("base", "range", "head", "tree")
ENT_MIN = 4.2
SEG_ENT_MIN = 3.5
HEX_ENT_MIN = 3.0
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".zip", ".gz", ".pyc")
SEC_DIR = "docs/source/security/"


def mask(v: str) -> str:
    return v[:4] + "*" * min(len(v) - 4, 8)


def entropy(t: str) -> float:
    return -sum(c / len(t) * math.log2(c / len(t)) for c in (t.count(x) for x in set(t)))


def mixed(t: str) -> bool:
    return any(c.isdigit() for c in t) and any(c.isalpha() for c in t)


def tok_kind(t: str, sha_ok: bool) -> str:
    if HEX.fullmatch(t):
        if sha_ok and len(t) in (40, 64) and t == t.lower():
            return ""
        return "high-entropy-hex" if entropy(t) >= HEX_ENT_MIN else ""
    segs = [x for x in re.split(r"[-_]", t) if x]
    if len(segs) > 1:
        return "high-entropy-token" if any(len(x) >= 20 and mixed(x) and entropy(x) >= SEG_ENT_MIN for x in segs) else ""
    return "high-entropy-token" if mixed(t) and entropy(t) >= ENT_MIN else ""


def wrapped_hits(lines: list[str]) -> list[tuple[int, str, str]]:
    starts = []
    pos = 0
    for l in lines:
        starts.append(pos)
        pos += len(l.strip())
    joined = "".join(l.strip() for l in lines)
    ln = lambda i: max(j for j, st in enumerate(starts) if st <= i) + 1
    return [(ln(m.start()), k, m.group(0)) for k, r in KEY_PATS[:-1] for m in r.finditer(joined) if ln(m.start()) != ln(m.end() - 1)]


def review_cols(lines: list[str]) -> dict[int, bool]:
    out: dict[int, bool] = {}
    names: list[str] = []
    idx = -1
    for n, raw in enumerate(lines, 1):
        head = raw.startswith("   * - ")
        if head or (raw.startswith("     - ") and idx >= 0):
            idx = 0 if head else idx + 1
            cell = raw.split("- ", 1)[1].strip().strip("`").lower()
            if head and not names:
                names = [cell]
            elif len(names) > 0 and idx == len(names) and not out:
                names.append(cell)
            elif idx < len(names):
                out[n] = names[idx] in SHA_COLS
        elif raw.strip() and not raw.startswith("   "):
            idx = -1
    return out


def redact_text(text: str, name: str, sha_file: bool = False) -> list[str]:
    out: list[str] = []
    lines = text.splitlines()
    cols = review_cols(lines) if sha_file else {}
    found: list[tuple[int, int, str, str]] = [(ln, 0, k, v) for ln, k, v in wrapped_hits(lines)]
    for ln, raw in enumerate(lines, 1):
        hits = [(m.start(), k, m.group(0)) for k, r in KEY_PATS for m in r.finditer(raw)]
        spans = [(m.start(), m.end()) for _, _, v in hits for m in [re.search(re.escape(v), raw)] if m]
        for m in TOKEN.finditer(raw):
            if any(a <= m.start() < b for a, b in spans):
                continue
            ok = cols.get(ln, False) or bool(SHA_PRE.search(raw[: m.start()]))
            k = tok_kind(m.group(0), ok)
            if k:
                hits.append((m.start(), k, m.group(0)))
        found += [(ln, i, k, v) for i, k, v in hits]
    out += [f"{name}:{ln}: {k} {mask(v)}" for ln, _, k, v in sorted(found)]
    return out


def redact_scan(paths: list[Path], root: Path) -> list[str]:
    out: list[str] = []
    for p in paths:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            out.append(f"{p}: unreadable: {e.strerror}")
            continue
        out += redact_text(txt, str(p), p.as_posix().endswith(SEC_DIR + "reviews.rst"))
    return out


def skip_file(x: Path) -> bool:
    return x.suffix in SKIP_EXT or (x.suffix == ".svg" and SEC_DIR not in x.as_posix() + "/")


def redact_paths(repo: Path, paths: list[str], feat: str, run: str) -> list[Path]:
    if paths:
        roots = [Path(x) if Path(x).is_absolute() else repo / x for x in paths]
    else:
        roots = [repo / "docs/source/security"]
        if feat and run:
            roots += sorted((repo / "docs/source/design_log").glob(f"{log_name(feat, run)}*.rst"))
    out: list[Path] = []
    for r in roots:
        out += sorted(x for x in r.rglob("*") if x.is_file() and not skip_file(x)) if r.is_dir() else [r]
    return out

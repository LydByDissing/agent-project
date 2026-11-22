# [origin ref=llm-dsl-2zv1.1,llm-dsl-2zv1.3 req=REQ-SECURITY-REVIEW-013,REQ-SECURITY-REVIEW-003,REQ-SECURITY-REVIEW-008,REQ-SECURITY-REVIEW-011 c4=sdd_skills/security_review]
#   [intent]Parses threat, risk and review records and feature needs from the docs tree and validates analysis findings against them.[/intent]
#   [inv]validate_findings returns one message per violated rule naming the finding id; it never raises on malformed finding fields.[/inv]
#   [inv]run_check returns an empty error list only when every REQ-008/011 rule holds; each failed rule adds a message naming its cause.[/inv]
# [/origin]

import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

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
    out: list[dict] = []
    cur = None
    last = None
    body = False
    for ln, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = DIRECTIVE.match(raw)
        if m:
            cur = {"type": m.group(1), "title": m.group(2).strip(), "file": str(path), "line": ln, "opts": {}}
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
    return [r for r in now if r not in old]


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
    reb = [r for r in recs if r.get("stage") == "rebase" and "operator" in r.get("outcome", "").lower() and r.get("base")]
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
        errs += [f"threat {t['opts'].get('id')} is open without a decision for run {run}" for t in lt if t["opts"].get("status") == "open" and not has_decision(t, run)]
    else:
        errs += [f"threat {t['opts'].get('id')} is open" for t in lt if t["opts"].get("status") == "open"]
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

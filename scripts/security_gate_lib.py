# [origin ref=llm-dsl-2zv1.1 req=REQ-SECURITY-REVIEW-013,REQ-SECURITY-REVIEW-003 c4=sdd_skills/security_review]
#   [intent]Parses threat, risk and review records and feature needs from the docs tree and validates analysis findings against them.[/intent]
#   [inv]validate_findings returns one message per violated rule naming the finding id; it never raises on malformed finding fields.[/inv]
# [/origin]

import json
import re
from pathlib import Path

SEVERITIES = ("crit", "high", "med", "low")
STRIDE_LETTERS = "STRIDE"
FIELDS = ("id", "severity", "stride", "element", "anchor", "threat", "mitigation", "links")
DIRECTIVE = re.compile(r"^\.\. (feat|req|threat|risk)::\s*(.*)$")
OPT = re.compile(r"^\s+:([a-z0-9_]+):\s*(.*)$")
THREAT_ID = re.compile(r"^THREAT-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3}$")
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


def parse_reviews(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[list[str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s.startswith("* - "):
            rows.append([s[4:].strip()])
        elif s.startswith("- ") and rows:
            rows[-1].append(s[2:].strip())
        elif s and rows and raw.startswith("     ") and rows[-1]:
            rows[-1][-1] = f"{rows[-1][-1]} {s}"
    keys = ("run", "stage", "review", "range", "findings", "outcome")
    return [dict(zip(keys, r)) for r in rows if r and RUN_ID.match(r[0])]


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
            if not THREAT_ID.match(nid) or not nid.startswith(f"THREAT-{want}-"):
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

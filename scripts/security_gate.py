# [origin ref=llm-dsl-2zv1.1,llm-dsl-2zv1.3,llm-dsl-2zv1.5,llm-dsl-2zv1.7,llm-dsl-2zv1.16 req=REQ-SECURITY-REVIEW-013,REQ-SECURITY-REVIEW-003,REQ-SECURITY-REVIEW-008,REQ-SECURITY-REVIEW-011,REQ-SECURITY-REVIEW-009,REQ-SECURITY-REVIEW-010 c4=sdd_skills/security_review]
#   [intent]Command line entry for the security gate script; validate checks records and findings, check gates a phase move on the review record, base, tree hash and protected-set rules, append-only fails when security records were removed or altered since given commits, redact-check fails on likely credentials in security outputs without echoing them.[/intent]
# [/origin]

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import security_gate_lib as lib

DOCS = Path(__file__).resolve().parent.parent / "docs" / "source"


def cmd_validate(a) -> int:
    docs = Path(a.docs)
    data = lib.load(docs)
    errs = [] if lib.feat_exists(data, a.feature) else [f"feature {a.feature} not found in {docs / 'specs'}"]
    errs += lib.check_records(data)
    if a.findings:
        try:
            fs = lib.load_findings(Path(a.findings))
        except (OSError, ValueError) as e:
            errs.append(f"findings unreadable: {e}")
        else:
            errs += lib.validate_findings(fs, data, a.feature)
    print(f"feature {a.feature}: {len(data['threats'])} threats, {len(data['risks'])} risks, {len(data['reviews'])} review records")
    for e in errs:
        print(f"ERROR {e}", file=sys.stderr)
    return 1 if errs else 0


def cmd_check(a) -> int:
    repo = Path(a.repo).resolve()
    docs = Path(a.docs) if a.docs else repo / "docs" / "source"
    try:
        epic = lib.load_epic(a.bd_json, a.epic)
    except (OSError, ValueError) as e:
        print(f"ERROR epic unreadable: {e}", file=sys.stderr)
        return 1
    errs, base = lib.run_check(repo, docs, a.feature, a.stage, a.epic, a.main, epic)
    if base and not os.environ.get(lib.REEXEC_ENV):
        st = lib.script_state(repo, base)
        if st == "absent":
            print(lib.BOOTSTRAP_LINE)
        elif st == "differs":
            argv = ["check", "--feature", a.feature, "--stage", a.stage, "--epic", a.epic, "--main", a.main, "--repo", str(repo), "--docs", str(docs)]
            return lib.reexec_base(repo, base, argv + (["--bd-json", a.bd_json] if a.bd_json else []))
    print(f"check {a.feature} stage {a.stage}: {'FAIL' if errs else 'ok'}")
    for e in errs:
        print(f"ERROR {e}", file=sys.stderr)
    return 1 if errs else 0


def cmd_base_path(a) -> int:
    repo = Path(a.repo).resolve()
    run = a.run
    if not run and a.epic:
        try:
            runs = lib.label_vals(lib.load_epic(a.bd_json, a.epic), "run")
        except (OSError, ValueError) as e:
            print(f"ERROR epic unreadable: {e}", file=sys.stderr)
            return 1
        run = runs[0] if len(runs) == 1 else ""
    if not run:
        rc, txt = lib.git(repo, "show", f"HEAD:{lib.REVIEWS_REL}")
        rows = lib.parse_reviews_text(txt) if rc == 0 else []
        run = rows[-1]["run"] if rows else ""
    lines = lib.base_path_info(repo, run) if run else []
    if not lines:
        print(f"ERROR no effective base found for run {run or '?'}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


def cmd_tree_hash(a) -> int:
    print(lib.tree_hash(Path(a.repo).resolve(), a.feature, a.run))
    return 0


def cmd_append_only(a) -> int:
    repo = Path(a.repo).resolve()
    since = [x for x in (a.since or "").split(",") if x] or lib.default_since(repo, a.run)
    errs = lib.run_append_only(repo, a.run, since, a.working_tree)
    print(f"append-only run {a.run} since {','.join(x[:8] for x in since) or '-'}: {'FAIL' if errs else 'ok'}")
    for e in errs:
        print(f"ERROR {e}", file=sys.stderr)
    return 1 if errs else 0


def cmd_redact(a) -> int:
    repo = Path(a.repo).resolve()
    files = lib.redact_paths(repo, a.paths or [], a.feature or "", a.run or "") + [Path(x) for x in a.text_file or []]
    errs = lib.redact_scan(files, repo)
    print(f"redact-check {len(files)} files: {'FAIL' if errs else 'ok'}")
    for e in errs:
        print(f"ERROR {e}", file=sys.stderr)
    return 1 if errs else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="security_gate")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--feature", required=True)
    v.add_argument("--findings")
    v.add_argument("--docs", default=str(DOCS))
    v.set_defaults(fn=cmd_validate)
    c = sub.add_parser("check")
    c.add_argument("--feature", required=True)
    c.add_argument("--stage", required=True, choices=("design", "post"))
    c.add_argument("--epic", required=True)
    c.add_argument("--main", default="main")
    c.add_argument("--repo", default=str(DOCS.parent.parent))
    c.add_argument("--docs")
    c.add_argument("--bd-json")
    c.set_defaults(fn=cmd_check)
    t = sub.add_parser("tree-hash")
    t.add_argument("--feature", required=True)
    t.add_argument("--run", required=True)
    t.add_argument("--repo", default=str(DOCS.parent.parent))
    t.set_defaults(fn=cmd_tree_hash)
    b = sub.add_parser("base-path")
    b.add_argument("--repo", default=str(DOCS.parent.parent))
    b.add_argument("--epic")
    b.add_argument("--run")
    b.add_argument("--bd-json")
    b.set_defaults(fn=cmd_base_path)
    o = sub.add_parser("append-only")
    o.add_argument("--run", required=True)
    o.add_argument("--since")
    o.add_argument("--working-tree", action="store_true")
    o.add_argument("--repo", default=str(DOCS.parent.parent))
    o.set_defaults(fn=cmd_append_only)
    r = sub.add_parser("redact-check")
    r.add_argument("--paths", nargs="+")
    r.add_argument("--text-file", nargs="+")
    r.add_argument("--feature")
    r.add_argument("--run")
    r.add_argument("--repo", default=str(DOCS.parent.parent))
    r.set_defaults(fn=cmd_redact)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

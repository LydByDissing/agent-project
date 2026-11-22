# [origin ref=llm-dsl-2zv1.1 req=REQ-SECURITY-REVIEW-013,REQ-SECURITY-REVIEW-003 c4=sdd_skills/security_review]
#   [intent]Command line entry for the security gate script; validate parses the security records and checks analysis findings for form and references.[/intent]
# [/origin]

import argparse
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="security_gate")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--feature", required=True)
    v.add_argument("--findings")
    v.add_argument("--docs", default=str(DOCS))
    v.set_defaults(fn=cmd_validate)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

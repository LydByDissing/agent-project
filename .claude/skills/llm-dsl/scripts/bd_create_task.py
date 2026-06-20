#!/usr/bin/env python3
"""Create a bd issue with DSL body."""

import sys
import argparse
import os

sys.path.insert(0, os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

from src.bd_runner import bd_create


def main():
    parser = argparse.ArgumentParser(description="Create a bd issue with DSL body")
    parser.add_argument("--title", "-t", required=True, help="Issue title")
    parser.add_argument("--body", "-b", help="DSL body string")
    parser.add_argument("--body-file", "-f", help="Read body from file")
    parser.add_argument("--agent", "-a", help="Agent role label (e.g. coder, reviewer)")
    parser.add_argument("--schema", "-s", help="Schema label (e.g. code-task)")
    parser.add_argument("--run-id", "-r", help="Run ID label for crash recovery")
    parser.add_argument("--depends-on", "-d", nargs="+", help="Dependency issue IDs")
    parser.add_argument("--acceptance", "-acc", nargs="+", help="Acceptance criteria")
    args = parser.parse_args()

    if args.body_file:
        body = Path(args.body_file).read_text()
    elif args.body:
        body = args.body
    else:
        body = sys.stdin.read()

    labels = []
    if args.agent:
        labels.append(f"agent={args.agent}")
    if args.schema:
        labels.append(f"schema={args.schema}")
    if args.run_id:
        labels.append(f"run={args.run_id}")

    bd_id = bd_create(
        title=args.title,
        body=body,
        labels=labels or None,
        acceptance=args.acceptance,
        deps=args.depends_on,
    )

    if bd_id:
        print(bd_id)
    else:
        print("Failed to create issue", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

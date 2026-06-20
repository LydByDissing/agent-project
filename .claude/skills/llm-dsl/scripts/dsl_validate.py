#!/usr/bin/env python3
"""Validate DSL against a schema."""

import sys
import argparse
import os

sys.path.insert(0, os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

from src.dsl_parser import parse_dsl, DslParseError


def _extract_dsl(text: str) -> str:
    for start_tag in ["[result", "[task"]:
        idx = text.find(start_tag)
        if idx != -1:
            close = "[/" + start_tag[1:] + "]"
            end = text.rfind(close)
            if end != -1:
                return text[idx:end + len(close)]
    return ""


def main():
    parser = argparse.ArgumentParser(description="Validate LLM-DSL")
    parser.add_argument("--file", "-f", help="Read DSL from file")
    parser.add_argument("--schema", "-s", help="Schema name (for error messages)")
    args = parser.parse_args()

    text = Path(args.file).read_text() if args.file else sys.stdin.read()
    dsl = _extract_dsl(text)
    if not dsl:
        print("Error: No DSL found", file=sys.stderr)
        sys.exit(1)

    try:
        parsed = parse_dsl(dsl)
        print(f"OK: Valid DSL (tag={parsed.tag}, attrs={list(parsed.attrs.keys())})")
    except DslParseError as e:
        schema = args.schema or "unknown"
        print(f"FAIL [{schema}]: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

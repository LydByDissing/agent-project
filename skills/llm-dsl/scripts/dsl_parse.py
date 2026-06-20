#!/usr/bin/env python3
"""Parse DSL from stdin or file and output structured JSON."""

import sys
import json
import argparse
import os

sys.path.insert(0, os.environ.get("CLAUDE_PLUGIN_ROOT") or str(__import__("pathlib").Path(__file__).resolve().parents[3]))

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
    parser = argparse.ArgumentParser(description="Parse LLM-DSL from stdin or file")
    parser.add_argument("--file", "-f", help="Read DSL from file instead of stdin")
    parser.add_argument("--pretty", "-p", action="store_true", help="Pretty-print output")
    args = parser.parse_args()

    text = Path(args.file).read_text() if args.file else sys.stdin.read()
    dsl = _extract_dsl(text)
    if not dsl:
        print("Error: No DSL found in input", file=sys.stderr)
        sys.exit(1)

    try:
        parsed = parse_dsl(dsl)
        result = parsed.to_dict()
        print(json.dumps(result, indent=2) if args.pretty else json.dumps(result))
    except DslParseError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

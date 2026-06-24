#!/usr/bin/env python3
"""Render all PlantUML source files in docs/architecture/diagrams/ to SVG.

Usage (from project root):
    python <skill-path>/scripts/generate_diagrams.py [--docs-dir docs]

Requires plantuml on PATH. Install via:
    macOS:          brew install plantuml
    Ubuntu/Debian:  apt install plantuml
    Or set PLANTUML_JAR=/path/to/plantuml.jar to use the JAR directly.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_plantuml() -> list[str]:
    jar = os.environ.get("PLANTUML_JAR", "")
    if jar and Path(jar).exists():
        return ["java", "-jar", jar]
    if shutil.which("plantuml"):
        return ["plantuml"]
    return []


def render_file(puml_path: Path, plantuml_cmd: list[str]) -> bool:
    svg_path = puml_path.with_suffix(".svg")
    cmd = plantuml_cmd + ["-tsvg", "-o", str(puml_path.parent.resolve()), str(puml_path.resolve())]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR  {puml_path}")
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"         {line}")
        return False
    print(f"  OK     {puml_path} → {svg_path.name}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--docs-dir", default="docs", help="Path to the Sphinx docs directory (default: docs)")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    diagrams_dir = docs_dir / "architecture" / "diagrams"

    if not diagrams_dir.exists():
        print(f"Diagrams directory not found: {diagrams_dir}")
        print("Run bootstrap_sphinx.py first.")
        sys.exit(1)

    plantuml_cmd = find_plantuml()
    if not plantuml_cmd:
        print("plantuml not found. Install it and try again:")
        print("  macOS:          brew install plantuml")
        print("  Ubuntu/Debian:  apt install plantuml")
        print("  JAR:            export PLANTUML_JAR=/path/to/plantuml.jar")
        sys.exit(1)

    puml_files = sorted(diagrams_dir.rglob("*.puml"))
    if not puml_files:
        print(f"No .puml files found under {diagrams_dir}")
        sys.exit(0)

    print(f"Rendering {len(puml_files)} diagram(s) using: {' '.join(plantuml_cmd)}\n")

    success, failed = 0, 0
    for puml_path in puml_files:
        if render_file(puml_path, plantuml_cmd):
            success += 1
        else:
            failed += 1

    print(f"\n{success} rendered, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

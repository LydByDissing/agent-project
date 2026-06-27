#!/usr/bin/env python3
"""Render all PlantUML source files in docs/architecture/diagrams/ to SVG.

Usage (from project root):
    python <skill-path>/scripts/generate_diagrams.py [--docs-dir docs]

PlantUML is resolved in order:
  1. PLANTUML_JAR env var (explicit path to .jar)
  2. plantuml on PATH
  3. ~/.local/share/plantuml/plantuml.jar (auto-downloaded if missing)
"""

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

PLANTUML_DOWNLOAD_URL = "https://github.com/plantuml/plantuml/releases/latest/download/plantuml.jar"
PLANTUML_JAR_CACHE = Path.home() / ".local" / "share" / "plantuml" / "plantuml.jar"


def _java_available() -> bool:
    return shutil.which("java") is not None


def _download_plantuml() -> Path:
    PLANTUML_JAR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading PlantUML from {PLANTUML_DOWNLOAD_URL} ...")
    urllib.request.urlretrieve(PLANTUML_DOWNLOAD_URL, PLANTUML_JAR_CACHE)
    print(f"Saved to {PLANTUML_JAR_CACHE}")
    return PLANTUML_JAR_CACHE


def find_plantuml() -> list[str]:
    jar = os.environ.get("PLANTUML_JAR", "")
    if jar and Path(jar).exists():
        return ["java", "-jar", jar]
    if shutil.which("plantuml"):
        return ["plantuml"]
    if not _java_available():
        print("java is not on PATH — required to run the PlantUML jar.")
        print("Install Java (e.g. apt install default-jre) and re-run.")
        sys.exit(1)
    jar_path = PLANTUML_JAR_CACHE if PLANTUML_JAR_CACHE.exists() else _download_plantuml()
    return ["java", "-jar", str(jar_path)]


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
    parser.add_argument("--docs-dir", default="docs/source", help="Path to the Sphinx source directory (default: docs/source)")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    diagrams_dir = docs_dir / "architecture" / "diagrams"

    if not diagrams_dir.exists():
        print(f"Diagrams directory not found: {diagrams_dir}")
        print("Run bootstrap_sphinx.py first.")
        sys.exit(1)

    plantuml_cmd = find_plantuml()

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

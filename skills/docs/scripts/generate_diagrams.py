#!/usr/bin/env python3
# [origin ref=llm-dsl-gu1y.13 req=REQ-OPERATOR-EDU-003 c4=sdd_skills/plan_skill]
#   [intent]Render PlantUML sources to SVG for the Sphinx docs site or, with --dir, for every .puml under a directory, failing when a rendered SVG carries a PlantUML warning banner[/intent]
# [/origin]
"""Render all PlantUML source files in docs/source/architecture/diagrams/ to SVG.

Usage (from project root):
    python <skill-path>/scripts/generate_diagrams.py [--docs-dir docs]
    python <skill-path>/scripts/generate_diagrams.py --dir learn

With --dir, every .puml under the directory is rendered to an SVG next to its
source, and the run fails if any SVG carries a PlantUML warning or deprecation
banner.

PlantUML is resolved in order:
  1. PLANTUML_JAR env var (explicit path to .jar)
  2. plantuml on PATH
  3. ~/.local/share/plantuml/plantuml.jar (auto-downloaded if missing)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

PLANTUML_DOWNLOAD_URL = "https://github.com/plantuml/plantuml/releases/latest/download/plantuml.jar"
PLANTUML_JAR_CACHE = Path.home() / ".local" / "share" / "plantuml" / "plantuml.jar"
SVG_NS = "{http://www.w3.org/2000/svg}"
WARNING_MARKERS = [
    re.compile(r"^Please\s+use\s+CSS\s+style\s+instead\s+of\s+skinparam\b"),
    re.compile(r"^Syntax\s+Error\?"),
]


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


def svg_warnings(svg_path: Path) -> list[str]:
    root = ET.parse(svg_path).getroot()
    texts = ["".join(el.itertext()) for el in root.iter(f"{SVG_NS}text")]
    return [txt for txt in texts if any(rx.search(txt) for rx in WARNING_MARKERS)]


def render_file(puml_path: Path, plantuml_cmd: list[str], strict: bool = False) -> bool:
    svg_path = puml_path.with_suffix(".svg")
    cmd = plantuml_cmd + ["-tsvg", "-o", str(puml_path.parent.resolve()), str(puml_path.resolve())]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR  {puml_path}")
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"         {line}")
        return False
    if strict and not svg_path.exists():
        print(f"  ERROR  {puml_path}")
        print(f"         expected {svg_path.name} next to source; name the @startuml block after the file stem")
        return False
    if strict:
        warns = svg_warnings(svg_path)
        if warns:
            print(f"  ERROR  {puml_path}")
            for w in warns:
                print(f"         PlantUML warning in {svg_path.name}: {w}")
            return False
    print(f"  OK     {puml_path} → {svg_path.name}")
    return True


def render_all(puml_files: list[Path], plantuml_cmd: list[str], strict: bool) -> int:
    failed = 0
    for puml_path in puml_files:
        if not render_file(puml_path, plantuml_cmd, strict):
            failed += 1
    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--docs-dir", default="docs/source", help="Path to the Sphinx source directory (default: docs/source)")
    parser.add_argument("--dir", default=None, help="Render every .puml under this directory next to its source; fail on PlantUML warnings")
    args = parser.parse_args()

    if args.dir is not None:
        root = Path(args.dir)
        if not root.is_dir():
            print(f"Directory not found: {root}")
            sys.exit(1)
        puml_files = sorted(root.rglob("*.puml"))
        if not puml_files:
            print(f"No .puml files found under {root}")
            sys.exit(0)
        plantuml_cmd = find_plantuml()
        print(f"Rendering {len(puml_files)} diagram(s) under {root} using: {' '.join(plantuml_cmd)}\n")
        failed = render_all(puml_files, plantuml_cmd, strict=True)
        print(f"\n{len(puml_files) - failed} rendered, {failed} failed.")
        if failed:
            sys.exit(1)
        return

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

    failed = render_all(puml_files, plantuml_cmd, strict=False)
    success = len(puml_files) - failed

    print(f"\n{success} rendered, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

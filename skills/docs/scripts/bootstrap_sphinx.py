# [origin ref=llm-dsl-5db req=REQ-DESIGN-CHAT-003 c4=sdd_skills/docs_skill]
#   [intent]Bootstrap script that creates the Sphinx documentation site structure with design log support[/intent]
# [/origin]

#!/usr/bin/env python3
"""Bootstrap a Sphinx + sphinx-needs documentation site in ./docs/ for SDD projects.

Creates the full structure for C4 architecture diagrams and sphinx-needs
requirements (features, requirements, ADRs). Idempotent: safe to run multiple
times. Skips files that already exist.

Also creates docs/.venv and installs docs/requirements.txt into it so Sphinx
never touches the system Python.
"""

import json
import subprocess
import sys
from pathlib import Path


DOCS_DIR = Path("docs")
SOURCE_DIR = DOCS_DIR / "source"

CONF_PY = '''\
project = "{project_name}"
author = "Architecture Team"
release = "0.1.0"

extensions = ["sphinx_needs"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]

# sphinx-needs: custom types for SDD
needs_types = [
    dict(directive="feat", title="Feature", prefix="FEAT-", color="#BFD8D2", style="node"),
    dict(directive="req", title="Requirement", prefix="REQ-", color="#FEDCD2", style="node"),
    dict(directive="adr", title="Architecture Decision Record", prefix="ADR-", color="#DF744A", style="node"),
]

# Extra fields beyond the sphinx-needs defaults (sphinx-needs >= 2.0 dict format)
_str_field = {{"schema": {{"type": "string"}}, "default": ""}}
needs_fields = {{
    "rationale":    {{**_str_field, "description": "WHY this requirement or decision exists"}},
    "acceptance":   {{**_str_field, "description": "Testable criterion, copied verbatim into bd task [accept]"}},
    "non_goal":     {{**_str_field, "description": "What this requirement explicitly does NOT cover"}},
    "c4_component": {{**_str_field, "description": "C4 L3 component id that owns this requirement"}},
    "c4_container": {{**_str_field, "description": "C4 L2 container this component lives in"}},
    "c4_scope":     {{**_str_field, "description": "ADR: space-separated component/container ids, or 'system'"}},
}}

needs_id_required = True
needs_id_regex = "^(FEAT|REQ|ADR)-[A-Z0-9-]+"
needs_default_layout = "clean"
'''

REQUIREMENTS_TXT = '''\
sphinx>=7.0
furo
sphinx-needs>=2.0
sphinx-autobuild
'''

MAKEFILE = '''\
SPHINXOPTS    ?=
SPHINXBUILD   ?= .venv/bin/sphinx-build
SOURCEDIR     = source
BUILDDIR      = _build

help:
\t@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help live Makefile

live:
\t.venv/bin/sphinx-autobuild "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS)

%: Makefile
\t@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
'''

INDEX_RST = '''\
.. _{project_name_slug}-docs:

{project_name}
{underline}

.. toctree::
   :maxdepth: 2
   :caption: Architecture

   architecture/index

.. toctree::
   :maxdepth: 2
   :caption: Specifications

   specs/index

.. toctree::
   :maxdepth: 1
   :caption: Design Log

   design_log/index

.. toctree::
   :maxdepth: 1
   :caption: About

   about
'''

ABOUT_RST = '''\
About
=====

This documentation is maintained using the **SDD docs skill**.

Architecture diagrams follow the `C4 model <https://c4model.com>`_ and
`ArchiMate <https://www.opengroup.org/archimate-forum>`_, authored in
`PlantUML <https://plantuml.com>`_ and pre-rendered to SVG.

Requirements are tracked with `sphinx-needs <https://sphinx-needs.com>`_ using
three directive types:

- ``.. feat::`` — a user-facing feature (groups requirements)
- ``.. req::`` — a single requirement belonging to a feature
- ``.. adr::`` — an architecture decision record
'''

ARCH_INDEX_RST = '''\
Architecture
============

System architecture documented using the `C4 model <https://c4model.com>`_
and `ArchiMate <https://www.opengroup.org/archimate-forum>`_.

Diagrams are authored as PlantUML source files (``diagrams/*.puml``) and
pre-rendered to SVG. To regenerate all diagrams run::

   python <skill-path>/scripts/generate_diagrams.py

.. toctree::
   :maxdepth: 2

   context
   containers
'''

CONTEXT_RST = '''\
System Context
==============

.. note::

   **Status: draft** — run the docs skill C4 interview to populate this page.

The system context diagram shows the system in scope and its relationships
with users and external systems.

.. image:: diagrams/context.svg
   :alt: System Context Diagram
   :align: center
   :width: 100%

Elements
--------

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Name
     - Type
     - Purpose
   * - *TBD*
     - *TBD*
     - *TBD*

Key Relationships
-----------------

*TBD*

Assumptions & Open Questions
-----------------------------

* [ ] To be captured during architecture interview
'''

CONTAINERS_RST = '''\
Containers
==========

.. note::

   **Status: draft** — run the docs skill C4 interview to populate this page.

The container diagram zooms into the system boundary and shows the major
deployable units: applications, services, and data stores.

.. image:: diagrams/containers.svg
   :alt: Container Diagram
   :align: center
   :width: 100%

Elements
--------

.. list-table::
   :header-rows: 1
   :widths: 20 20 20 40

   * - Name
     - Type
     - Technology
     - Purpose
   * - *TBD*
     - *TBD*
     - *TBD*
     - *TBD*

Key Relationships
-----------------

*TBD*

Assumptions & Open Questions
-----------------------------

* [ ] To be captured during architecture interview
'''

CONTEXT_PUML = '''\
@startuml context
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Context.puml

title System Context: [System Name]

Person(user, "[Role]", "[Description]")
System_Boundary(sys, "[System Name]") {
    System(core, "[System Name]", "[Purpose]")
}
System_Ext(ext1, "[External System]", "[Purpose]")

Rel(user, core, "[Interaction]", "[Protocol]")
Rel(core, ext1, "[Interaction]", "[Protocol]")

SHOW_LEGEND()
@enduml
'''

CONTAINERS_PUML = '''\
@startuml containers
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Container.puml

title Container Diagram: [System Name]

Person(user, "[Role]", "[Description]")

System_Boundary(sys, "[System Name]") {
    Container(app, "[App Name]", "[Tech]", "[Responsibility]")
    ContainerDb(db, "[DB Name]", "[Tech]", "[What it stores]")
}

System_Ext(ext, "[External]", "[Purpose]")

Rel(user, app, "[How]", "[Protocol]")
Rel(app, db, "[How]", "SQL")
Rel(app, ext, "[How]", "[Protocol]")

SHOW_LEGEND()
@enduml
'''

SPECS_INDEX_RST = '''\
Specifications
==============

Features, requirements, and architecture decision records (ADRs).

All items are tracked with `sphinx-needs <https://sphinx-needs.com>`_.

Requirement IDs follow the pattern ``REQ-<FEATURE>-<NNN>``.
Feature IDs follow the pattern ``FEAT-<NAME>``.
ADR IDs follow the pattern ``ADR-<NNN>``.

.. toctree::
   :maxdepth: 2

   features/index
   adrs/index

Traceability Matrix
-------------------

All requirements across all features:

.. needtable::
   :types: req
   :columns: id, title, status, c4_component
   :style: table
'''

DESIGN_LOG_INDEX_RST = '''\
Design Log
==========

Record of design decisions made during development. Each design log entry
documents the decision, its rationale, and alternatives considered.

Design log entries are organized by feature and named ``FEAT-<NAME>-<RRR>.rst``,
where ``FEAT-<NAME>`` is the feature ID and ``<RRR>`` is a revision number.

Quick Lookup
------------

Find entries for a feature::

   grep -r "FEAT-XXX" docs/source/design_log/

Find entries mentioning a component::

   grep -r "c4_component: component_id" docs/source/design_log/

.. toctree::
   :maxdepth: 1

'''

FEATURES_INDEX_RST = '''\
Features
========

.. toctree::
   :maxdepth: 1

'''

ADRS_INDEX_RST = '''\
Architecture Decision Records
==============================

ADRs capture significant architectural decisions: what was decided, why,
and what alternatives were rejected.

.. toctree::
   :maxdepth: 1

'''

FEATURE_EXAMPLE_RST = '''\
Example Feature
===============

.. note::

   This is an example. Replace with real feature content.
   Copy this file to ``docs/specs/features/<feature-name>.rst``.

.. feat:: Example Feature
   :id: FEAT-EXAMPLE
   :status: draft

   One paragraph describing the feature from the user\'s perspective.
   What problem does it solve? Who benefits?

Requirements
------------

.. req:: Example requirement
   :id: REQ-EXAMPLE-001
   :links: FEAT-EXAMPLE
   :status: draft
   :rationale: Why this requirement exists — the business driver.
   :acceptance: Given X, when Y, then Z (testable, measurable).
   :non_goal: What this requirement explicitly does not cover.
   :c4_component: component_id
   :c4_container: container_id

   The system shall [behaviour]. Written as a falsifiable statement of
   observable system behaviour.
'''

ADR_EXAMPLE_RST = '''\
ADR-001: Example Decision
=========================

.. adr:: Example Decision
   :id: ADR-001
   :status: accepted
   :c4_scope: system

   **Context**: Describe the situation and forces at play.

   **Decision**: State the decision clearly.

   **Rationale**: Why this option over the alternatives?

   **Consequences**: What becomes easier or harder as a result?

   **Alternatives considered**:

   - Option A — rejected because …
   - Option B — rejected because …

.. note::

   ``c4_scope``: space-separated list of C4 component or container ids this
   decision applies to. Use ``system`` for decisions that apply everywhere.
   Examples: ``auth_service``, ``backend auth_service``, ``system``.
'''


def setup_venv(docs_dir: Path) -> None:
    venv_dir = docs_dir / ".venv"
    if venv_dir.exists():
        print(f"  skip   {venv_dir}  (already exists)")
        return
    print(f"  create {venv_dir}  (Python venv)")
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    pip = venv_dir / "bin" / "pip"
    req = docs_dir / "requirements.txt"
    print(f"  pip install -r {req} (into venv) ...")
    subprocess.run([str(pip), "install", "-r", str(req), "-q"], check=True)
    print(f"  venv ready: {venv_dir}")


def write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        print(f"  skip   {path}  (already exists)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"  create {path}")


def detect_project_name() -> str:
    cwd = Path.cwd()
    for candidate in [cwd / "pyproject.toml", cwd / "setup.cfg"]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                if line.startswith("name"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip().strip('"').strip("'")
    pkg = cwd / "package.json"
    if pkg.exists():
        data = json.loads(pkg.read_text())
        if "name" in data:
            return data["name"]
    return cwd.name


def main() -> None:
    project_name = detect_project_name()
    underline = "=" * len(project_name)
    project_name_slug = project_name.lower().replace(" ", "-").replace("_", "-")

    print(f"Bootstrapping Sphinx + sphinx-needs docs site for: {project_name}")
    print(f"Target directory: {DOCS_DIR.resolve()}\n")

    # docs/ root: Makefile, requirements.txt, venv (source lives in docs/source/)
    write_if_missing(DOCS_DIR / "requirements.txt", REQUIREMENTS_TXT)
    write_if_missing(DOCS_DIR / "Makefile", MAKEFILE)

    # docs/source/: all RST + conf.py
    write_if_missing(SOURCE_DIR / "conf.py", CONF_PY.format(project_name=project_name))
    write_if_missing(
        SOURCE_DIR / "index.rst",
        INDEX_RST.format(
            project_name=project_name,
            underline=underline,
            project_name_slug=project_name_slug,
        ),
    )
    write_if_missing(SOURCE_DIR / "about.rst", ABOUT_RST)
    write_if_missing(SOURCE_DIR / "_static" / ".gitkeep", "")
    write_if_missing(SOURCE_DIR / "_templates" / ".gitkeep", "")

    # Architecture section
    write_if_missing(SOURCE_DIR / "architecture" / "index.rst", ARCH_INDEX_RST)
    write_if_missing(SOURCE_DIR / "architecture" / "context.rst", CONTEXT_RST)
    write_if_missing(SOURCE_DIR / "architecture" / "containers.rst", CONTAINERS_RST)
    write_if_missing(SOURCE_DIR / "architecture" / "components" / ".gitkeep", "")
    write_if_missing(SOURCE_DIR / "architecture" / "diagrams" / "context.puml", CONTEXT_PUML)
    write_if_missing(SOURCE_DIR / "architecture" / "diagrams" / "containers.puml", CONTAINERS_PUML)

    # Specifications section (sphinx-needs)
    write_if_missing(SOURCE_DIR / "specs" / "index.rst", SPECS_INDEX_RST)
    write_if_missing(SOURCE_DIR / "specs" / "features" / "index.rst", FEATURES_INDEX_RST)
    write_if_missing(SOURCE_DIR / "specs" / "features" / "example.rst", FEATURE_EXAMPLE_RST)
    write_if_missing(SOURCE_DIR / "specs" / "adrs" / "index.rst", ADRS_INDEX_RST)
    write_if_missing(SOURCE_DIR / "specs" / "adrs" / "adr-001-example.rst", ADR_EXAMPLE_RST)

    # Design Log section
    write_if_missing(SOURCE_DIR / "design_log" / "index.rst", DESIGN_LOG_INDEX_RST)

    setup_venv(DOCS_DIR)

    print(f"""
Done. Next steps:
  1. Run the docs skill C4 interview to populate architecture pages.

  2. Add features and requirements under docs/source/specs/features/.

  3. Render diagrams to SVG:
       python3 <skill-path>/scripts/generate_diagrams.py

  4. Build the docs:
       cd {DOCS_DIR} && make html

  5. Live preview with auto-rebuild:
       cd {DOCS_DIR} && make live

  6. Open in browser:
       open {DOCS_DIR}/_build/html/index.html

Note: Sphinx runs from docs/.venv — no global pip installs needed.
""")


if __name__ == "__main__":
    main()

ADR-004: Lesson diagrams are committed as source plus pre-rendered SVG
======================================================================

.. adr:: Lesson diagrams are committed as source plus pre-rendered SVG
   :id: ADR-004
   :status: accepted
   :c4_scope: lesson_library learn_spa plan_skill

   **Context**: Lessons need advanced diagrams (C4, sequence, infra
   topology). Browser renderers cover only part of this.

   **Decision**: The plan phase writes diagram source (PlantUML, D2 or
   Mermaid) and renders it to SVG at generation time. Both are committed
   next to the lesson. The SPA shows SVGs only.

   **Rationale**: Any diagram tool can be used, the SPA stays simple, and
   lessons render the same everywhere without a renderer at view time.

   **Consequences**: Generation needs the renderer installed (PlantUML is
   already resolved by the docs skill's ``generate_diagrams.py``). The
   validator must catch an SVG older than its source.

   **Alternatives considered**:

   - Mermaid rendered in the browser: rejected. Too limited for C4 and
     infra diagrams.

ADR-001: Learning content lives in learn/, separate from the docs site
======================================================================

.. adr:: Learning content lives in learn/, separate from the docs site
   :id: ADR-001
   :status: accepted
   :c4_scope: learn_app lesson_library docs_site

   **Context**: FEAT-OPERATOR-EDU needs a store for generic teaching
   material. The repo already has a Sphinx site with good diagram support,
   which made it an obvious candidate.

   **Decision**: Lessons live in a top-level ``learn/`` folder in the
   project repo. They are never included in, linked from, or built by the
   Sphinx docs site.

   **Rationale**: The docs site is the project's specification (what this
   system is and must do), read by stakeholders and by the pipeline. The
   learn library is teaching material (general knowledge the operator may
   lack), read by one developer while waiting. Different purpose, different
   readers, different lifecycle.

   **Consequences**: The learn library needs its own validator and renderer
   (REQ-OPERATOR-EDU-002, -003, -011). Sphinx's diagram pipeline is not
   reused directly. Spec and teaching material cannot drift into each
   other.

   **Alternatives considered**:

   - Lessons as Sphinx pages with a quiz directive: rejected. The static
     site cannot write learner state or follow wave progress, and it would
     mix teaching material into the spec.
   - Sphinx-authored lessons served by a live server (hybrid): rejected
     for the same reason, and every content edit would need a Sphinx build.

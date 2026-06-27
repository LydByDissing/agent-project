FEAT-DESIGN-CHAT Design Session — run 0e02b3fb
===============================================

:Date: 2026-06-27
:Feature: FEAT-DESIGN-CHAT
:Run: 0e02b3fb
:GitHub Issue: #2
:c4_elements: sdd_skills docs_skill sdd_orchestrator
:Requirements: FEAT-DESIGN-CHAT REQ-DESIGN-CHAT-001 REQ-DESIGN-CHAT-002 REQ-DESIGN-CHAT-003

Interview Transcript
--------------------

**Agent**: When the issue says "design phase chat" — is this the conversation
between the developer and the Docs Skill during the docs interview, or the
broader Claude Code session including all pipeline phases?

**User**: This session just now, plus the docs chat. This is merely for
keeping record of the important design decision process.

**Agent**: Where should the transcript be stored? Options: under
``docs/design_log/FEAT-XXX-<run_id>.rst`` inside the Sphinx site; as a
standalone file in a ``design_log/`` directory at the repo root; or captured
to the beads epic as an attachment.

**User**: agreed (docs/design_log inside Sphinx site).

**Agent**: The issue says "reviewed when design changes are requested" — does
that mean it should be searchable (e.g., grep-able for a topic), or is
full-session access enough?

**User**: Should be searchable, so let's tag it of C4 L1 through L3 where
possible.

Design Decisions
----------------

- **Scope**: The full Claude Code session from ``/sdd #N`` invocation through
  docs phase completion (not plan/implement/arch-review). Rationale: the design
  rationale and rejected alternatives are what matter; later phases are
  mechanical execution.

- **Storage**: RST under ``docs/source/design_log/`` inside the Sphinx site.
  Rationale: co-locates with the spec it describes; Sphinx full-text search
  covers it; grep works on the source files.

- **Format**: Human-readable RST with a metadata header (``:c4_elements:``,
  ``:requirements:``) for grep-based discovery, followed by the raw Q&A
  transcript. No LLM post-processing.

- **Tagging**: C4 element IDs derived from sphinx-needs items written during
  the session (not extracted from prose), covering all three C4 levels present
  in the session. Rationale: deterministic — no ambiguity about what was
  "discussed" vs. what was formally captured.

- **Reference-only rule**: Design log content is never fed back into pipeline
  context. It is for human review when requirements change, not for re-priming
  future LLM agents.

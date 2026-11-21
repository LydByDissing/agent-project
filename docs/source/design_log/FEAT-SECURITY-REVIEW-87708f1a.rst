FEAT-SECURITY-REVIEW Design Session — run 87708f1a
==================================================

:Date: 2026-11-21
:Feature: FEAT-SECURITY-REVIEW
:Run: 87708f1a
:c4_elements: security_review sdd_orchestrator sdd_skills
:Requirements: FEAT-SECURITY-REVIEW REQ-SECURITY-REVIEW-001 REQ-SECURITY-REVIEW-002 REQ-SECURITY-REVIEW-003 REQ-SECURITY-REVIEW-004 REQ-SECURITY-REVIEW-005 REQ-SECURITY-REVIEW-006

Interview Transcript
--------------------

**User** (brief, raised during FEAT-OPERATOR-EDU arch-review): New
requirement, different task, track it in bd. When test and arch-review agents
have approved the work, a cyber security agent must analyse the architecture
and the resulting code. We also MUST run this agent when the initial design
is approved: when the docs are approved, a security agent reviews the
proposed changes to the code and architecture, because it is cheaper to catch
issues up front. Reset to docs if needed.

**Agent**: When the design-time review finds problems, should crit/high
findings reset to docs automatically, should every finding go to you, or
should any finding reset automatically?

**User**: Always ask me.

**Agent**: What should the security agent use: a STRIDE threat model, OWASP
checks on code, scanners when installed, dependency review?

**User**: STRIDE threat model and OWASP checks on code.

**Agent**: Which model: Opus, Sonnet escalating to Opus, or Sonnet?

**User**: Opus.

**Agent**: Where should results live: docs plus epic, epic only, or design log
only?

**User**: Docs plus epic.

Design Decisions
----------------

- **Placement**: new ``security-design`` phase after docs approval and before
  plan; new ``security-review`` phase after arch-review (REQ-001, REQ-004).
- **Gates**: the operator decides every finding; reset to docs only by
  operator choice (REQ-002, REQ-005).
- **Method**: STRIDE at design time, OWASP ASVS / Top 10 on code, no
  scanners, no dependency audit (ADR-005).
- **Model**: Opus always (ADR-005).
- **Storage**: ``threat`` and ``risk`` sphinx-needs types under
  ``docs/source/security/``, plus a ``[security]`` result on the epic
  (REQ-003).

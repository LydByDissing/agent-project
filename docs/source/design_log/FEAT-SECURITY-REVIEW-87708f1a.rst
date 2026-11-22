FEAT-SECURITY-REVIEW Design Session — run 87708f1a
==================================================

:Date: 2026-11-21
:Feature: FEAT-SECURITY-REVIEW
:Run: 87708f1a
:c4_elements: security_review sdd_orchestrator sdd_skills
:Requirements: FEAT-SECURITY-REVIEW REQ-SECURITY-REVIEW-001 REQ-SECURITY-REVIEW-002 REQ-SECURITY-REVIEW-003 REQ-SECURITY-REVIEW-004 REQ-SECURITY-REVIEW-005 REQ-SECURITY-REVIEW-006 REQ-SECURITY-REVIEW-007 REQ-SECURITY-REVIEW-008 REQ-SECURITY-REVIEW-009 REQ-SECURITY-REVIEW-010 REQ-SECURITY-REVIEW-011 REQ-SECURITY-REVIEW-012 REQ-SECURITY-REVIEW-013

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

Design-Time Security Gate (reset 1)
-----------------------------------

**Agent**: After docs approval, ran the design-time security review by hand
(Opus, read-only). It reported 12 findings, SD-01..SD-12: inline agent
exposed to prompt injection (crit); security phase skippable because
arch-review closes the epic and phase labels accumulate; unenforceable
operator gate; forgeable ``[security]`` block in bd; silent edits to threat
and risk records; ``mitigated`` without evidence; secret leakage into
published output (high); unbounded loops; Opus cost and silent truncation;
unscoped fix worker; untestable criteria (med); unvalidated findings (low).

**User**: Add all crit/high as requirements. Add all medium as
requirements. Add the low one as a requirement.

Decisions
~~~~~~~~~

- Reset to docs (``reset-count=1``). Findings recorded as
  THREAT-SDD-SKILLS-001..012, status ``open``.
- REQ-001..006 amended (SKILL.md diff as design input, explicit trust
  boundaries, ``noted`` status, id mapping, evidence for ``mitigated``,
  scoped and verified fix worker, single phase label, arch-review stops
  closing the run, resume refuses to skip a gate).
- New REQ-007 (read-only analysis sub-agent), REQ-008 (script-checked,
  operator-only gate; bd block hash-checked), REQ-009 (append-only records),
  REQ-010 (no secrets or exploit steps published), REQ-011 (base commit,
  scope and budget), REQ-012 (incremental re-review, bounded loops), REQ-013
  (findings validation).
- ADR-005 clarified: read-only analysis sub-agent; output credential guard
  is not a code scanner.

Design-Time Security Gate (review 2, reset 2)
---------------------------------------------

**Agent**: Ran the incremental re-review (Opus, read-only) over the reset-1
changes and the 12 open threats. Verdict: 4 threats adequately covered, 8
partly. Ten findings, SD2-01..SD2-10: the gate check passes when no review
ran; the enforcement code is editable by workers and there is no CI; "the
operator's own turn" is untestable and headless runs could treat issue text
as a turn; the ``base=`` label is forgeable (high); read-only is prompt-only;
the supersedes loophole; the redaction scope; in-session phase moves; the
sabotage check edits the real tree (med); small requirement gaps (low).

**User**: Add all four high findings as requirements. Add all medium and
low findings in the same reset. If a third review still finds issues, only
crit/high go back to docs.

Decisions
~~~~~~~~~

- Reset to docs (``reset-count=2``); the operator confirmed continuing past
  REQ-012's two-reset limit.
- New threats THREAT-SDD-SKILLS-013 (enforcement code editable) and -014
  (forgeable review anchor). Partial gaps folded into the links of
  existing threats.
- REQ-002..013 amended: review record with tree hash; protected set in
  RULES.md; gate script run from base when changed; interactive-only
  decisions with verbatim answers and final confirmation; check before every
  phase move and epic close; analysis agent with Read/Grep/Glob only and
  structured findings; superseding records inherit status; decision list per
  run; wider redaction scope with sha allowlist; sabotage in a throwaway
  worktree; base label verified against the merge-base; links must belong
  to the feature.
- Policy for review 3 in this run: crit/high reset to docs; med/low are
  recorded as noted.

Design-Time Security Gate (review 3, reset 3)
---------------------------------------------

**Agent**: Ran review 3 (incremental, Opus, read-only). 7 threats adequately
covered and 7 partly. Seven findings: implement workers can forge the gate's
RST inputs (SD3-01, high); the merge-base rule for the base breaks on stacked
branches, this run included (SD3-02, high); the hash covers its own record
and the post check is not bound to code (SD3-03); the gate script is absent at
the base on the first run (SD3-04); the protected set misses hooks, plugin
config, MCP config and pytest config (SD3-05); non-interactive detection is
undefined (SD3-06); process threats do not fit sabotage evidence (SD3-07).

**User**: Yes, reset 3. Fold SD3-03 and SD3-05 into the same pass and note
the rest. Then a short check of the SD3-01/02 edits, and on to plan.

Decisions
~~~~~~~~~

- Reset to docs (``reset-count=3``); the operator confirmed going past the
  REQ-012 limit again.
- REQ-006: wider protected set; the plan gate flags implement tasks that
  touch it; changes to it need an operator decision enforced by the check.
- REQ-008: hash excludes the security docs; the post check is bound to HEAD
  and to protected-set changes since the base.
- REQ-009: append-only covers review records.
- REQ-011: the base is the operator-confirmed fork point stored in the first
  review record; the label mirrors it; main's merge-base must be an
  ancestor of the base; re-recording after a rebase needs an operator
  decision. This run's base is ``a429fd8``.
- Noted: THREAT-SDD-SKILLS-015 (bootstrap gate script), -016
  (non-interactive detection), -017 (process-threat evidence).

Design-Time Security Gate (narrow check after reset 3)
------------------------------------------------------

**Agent**: Narrow check of the reset-3 edits. SD3-02 closed; SD3-01 has a
remaining gap fixable in implementation. Four findings, none critical: the
append-only test does not protect records created during the run (SD4-01);
forged edits can hide in legitimate protected-path changes (SD4-02); bd and
design-log commits break the post check (SD4-03); untestable wording around
the stored base and import scope (SD4-04). Conclusion: planning may proceed.

Decisions
~~~~~~~~~

- Per the operator's policy for this step, all four recorded as noted
  (THREAT-SDD-SKILLS-018..021). SD4-01 and SD4-02 become explicit acceptance
  checks in the plan.
- Design gate passed; the run advances to plan.

Implementation Review (request-changes)
---------------------------------------

**Agent**: The Opus reviewer returned request-changes: the protected set is
read from the working-tree RULES.md so a run can disable it (crit); the HEAD
script decides whether to re-run the base version; ``check --stage design``
compares against the current tree, so resume after implement deadlocks; the
sdd skill marks requirements implemented after closing the epic, breaking
every later post check; the learn-app suite went red after the threat-modeling
lesson was added (major); nine minor findings.

**User**: Fix the crit and the majors; file the minors as follow-ups.

Decisions
~~~~~~~~~

- REQ-SECURITY-REVIEW-008 clarified in place (operator choice, no docs
  reset): the design-stage tree hash is taken at the design record's head
  commit; the orchestrator, not the HEAD script, runs the base version; the
  protected set is read from RULES.md at the base, merged with defaults, and
  RULES.md is always protected.


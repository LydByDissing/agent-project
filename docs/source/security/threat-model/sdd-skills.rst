SDD Skills — Threat Model
=========================

Container: ``sdd_skills``. Threats recorded by the design-time security
review of FEAT-SECURITY-REVIEW (run 87708f1a, 2026-11-22): 001..012 from the
first review, 013..014 from review 2, 015..017 from review 3. 001..014 are
``open`` until the linked requirements are implemented and verified;
015..017 are ``noted`` by the operator and handled during implementation.

Trust boundaries
----------------

- Operator ↔ orchestrator (gate decisions).
- Orchestrator ↔ sub-agents (worker and analysis prompts, returned reports).
- Agents ↔ repository content: code, diffs, docs and GitHub issue text that
  an attacker may influence.
- Agents ↔ bd notes and labels (free text any agent can write).
- Docs site and GitHub (publication of security output).

Threats
-------

.. threat:: Inline security agent steered by injected text
   :id: THREAT-SDD-SKILLS-001
   :status: open
   :stride: E
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Analysis in a read-only sub-agent; content passed as data; embedded instructions reported as findings.
   :links: REQ-SECURITY-REVIEW-007

   The agent analysing attacker-influenced code, docs and issue text runs in the main context with shell, gh and bd write access, so injected instructions could steer its verdict or trigger actions.

.. threat:: Security phase skipped by ordering or label edits
   :id: THREAT-SDD-SKILLS-002
   :status: open
   :stride: E
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Single phase label; arch-review stops closing the run; resume refuses to skip a failing gate.
   :links: REQ-SECURITY-REVIEW-006, REQ-SECURITY-REVIEW-008

   arch-review closes the epic before security-review runs, and phase labels accumulate so any agent can add phase=done or phase=plan.

.. threat:: Operator decision not enforceable
   :id: THREAT-SDD-SKILLS-003
   :status: open
   :stride: R
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Findings written as open first; gate state checked by script; decisions only from the operator's own turn, rationale verbatim.
   :links: REQ-SECURITY-REVIEW-008, REQ-SECURITY-REVIEW-002

   The agent writes the findings, the gate summary and the decision record, so it can omit findings or invent decisions.

.. threat:: Forged security result in bd notes
   :id: THREAT-SDD-SKILLS-004
   :status: open
   :stride: S
   :c4_scope: security_review sdd_orchestrator
   :mitigation: bd block is a record only; gate state derived from the RST; block carries a hash re-checked on resume.
   :links: REQ-SECURITY-REVIEW-008

   Any agent can append a [security] block claiming approval; nothing authenticates its writer.

.. threat:: Silent edits to threats and accepted risks
   :id: THREAT-SDD-SKILLS-005
   :status: open
   :stride: T
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Append-only ids with supersedes; test against the base branch.
   :links: REQ-SECURITY-REVIEW-009

   Later reviews or the docs skill can delete a threat, flip its status or rewrite a risk rationale without trace.

.. threat:: Threat marked mitigated without evidence
   :id: THREAT-SDD-SKILLS-006
   :status: open
   :stride: T
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Mitigated needs file:line, test id and an orchestrator sabotage check, and is confirmed at the gate.
   :links: REQ-SECURITY-REVIEW-004

   The agent could set a threat to mitigated on its own claim, unseen by the operator.

.. threat:: Secret values or exploit steps published
   :id: THREAT-SDD-SKILLS-007
   :status: open
   :stride: I
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Secrets named by location only; redact-check before commit; no exploit steps; never post findings to GitHub.
   :links: REQ-SECURITY-REVIEW-010

   Reporting a found secret could copy its value into docs, bd notes or GitHub; open threats could publish exploit detail.

.. threat:: Unbounded reset and fix loops
   :id: THREAT-SDD-SKILLS-008
   :status: open
   :stride: D
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Incremental re-review; decided findings not re-raised; operator confirmation after 2 resets or 3 fix rounds.
   :links: REQ-SECURITY-REVIEW-012

   Each non-deterministic re-review can reword or add findings and neither loop has a limit.

.. threat:: Opus spend and silent truncation
   :id: THREAT-SDD-SKILLS-009
   :status: open
   :stride: D
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Exclusion list, size budget, unreviewed scope shown at the gate, token use recorded.
   :links: REQ-SECURITY-REVIEW-011

   Generated, binary, lock and vendored content inflates input, wasting spend and possibly exceeding context.

.. threat:: Fix worker weakens what it fixes
   :id: THREAT-SDD-SKILLS-010
   :status: open
   :stride: E
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Out paths limited to the finding's files plus one test; orchestrator verifies suites, scope and sabotage.
   :links: REQ-SECURITY-REVIEW-005, REQ-SECURITY-REVIEW-006

   The fix worker's brief comes from finding text; without scope limits it could weaken tests or edit security docs or skills.

.. threat:: Untestable criteria let gates pass on paper
   :id: THREAT-SDD-SKILLS-011
   :status: open
   :stride: T
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Recorded base sha, explicit trust boundaries, id mapping, noted status, SKILL.md diff as design input.
   :links: REQ-SECURITY-REVIEW-001, REQ-SECURITY-REVIEW-002, REQ-SECURITY-REVIEW-003, REQ-SECURITY-REVIEW-011

   No base commit, no trust-boundary list, an id format that breaks the needs regex, undefined 'note', and skill prompts never reviewed at design time.

.. threat:: Malformed or invented references in findings
   :id: THREAT-SDD-SKILLS-012
   :status: open
   :stride: R
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Validation helper before the gate; warnings as errors in the security docs.
   :links: REQ-SECURITY-REVIEW-013

   Unvalidated severity, STRIDE values, C4 ids or links enter published needs.

.. threat:: Enforcement code editable by workers
   :id: THREAT-SDD-SKILLS-013
   :status: open
   :stride: T
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Protected set in RULES.md that fix workers never write; changes to it are mandatory gate findings; gate script run from the base commit; append-only test run by the orchestrator before each gate commit.
   :links: REQ-SECURITY-REVIEW-005, REQ-SECURITY-REVIEW-006, REQ-SECURITY-REVIEW-008, REQ-SECURITY-REVIEW-009

   The gate script, the append-only test and the Sphinx config sit in paths
   workers can edit, and there is no CI, so any worker could make the
   safeguards always pass.

.. threat:: Review anchor forgeable through bd labels
   :id: THREAT-SDD-SKILLS-014
   :status: open
   :stride: T
   :c4_scope: security_review sdd_orchestrator
   :mitigation: Exactly one base label, ancestor of HEAD, equal to the merge-base with main; last-reviewed sha taken from the committed review record, never bd.
   :links: REQ-SECURITY-REVIEW-011, REQ-SECURITY-REVIEW-012

   Any agent can move or duplicate the ``base=`` label and so empty the review
   diff; the "last review" anchor for incremental re-reviews was undefined.

.. threat:: Gate script unverified on first run
   :id: THREAT-SDD-SKILLS-015
   :status: noted
   :stride: T
   :c4_scope: security_review
   :decided_by: operator
   :run: 87708f1a
   :mitigation: Implementation: if the script is absent at the base, show a mandatory "gate script unverified (bootstrap)" finding at both gates; otherwise run the base version from a throwaway worktree with python -I.
   :links: REQ-SECURITY-REVIEW-008

   Running the gate script "from the base commit" is meaningless when it did
   not exist there, as in run 87708f1a, and a base copy run from the HEAD tree
   still imports HEAD modules and config. Noted 2026-11-22 (review 3, SD3-04).

.. threat:: Non-interactive session not defined
   :id: THREAT-SDD-SKILLS-016
   :status: noted
   :stride: D
   :c4_scope: sdd_orchestrator
   :decided_by: operator
   :run: 87708f1a
   :mitigation: Implementation: treat a missing or failing question tool as non-interactive; document the two gate pauses in the sdd SKILL.md and README with a doc-contract test.
   :links: REQ-SECURITY-REVIEW-008

   The requirement to refuse non-interactive sessions does not say how one is
   detected; auto, bypass or headless modes may lack or auto-answer the
   question tool. Noted 2026-11-22 (review 3, SD3-06).

.. threat:: Process threats do not fit sabotage evidence
   :id: THREAT-SDD-SKILLS-017
   :status: noted
   :stride: R
   :c4_scope: security_review
   :decided_by: operator
   :run: 87708f1a
   :mitigation: Implementation: accept a doc-contract or behaviour test plus a sabotage patch for process threats, or operator confirmation of "mitigated by requirement".
   :links: REQ-SECURITY-REVIEW-004, REQ-SECURITY-REVIEW-005

   Loop caps, budgets and untestable-criteria threats cannot be shown by
   "disable the mitigation and a test fails", which invites marking them noted
   instead of mitigated. Noted 2026-11-22 (review 3, SD3-07).


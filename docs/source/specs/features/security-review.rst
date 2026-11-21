Security Review — Design-Time and Post-Implementation
=====================================================

.. feat:: Security Review — Design-Time and Post-Implementation
   :id: FEAT-SECURITY-REVIEW
   :status: approved

   Adds a security agent to the SDD pipeline at two points. The first runs
   right after the operator approves the docs, before planning. It reviews
   the proposed architecture and requirements, where a flaw is cheapest to
   fix, and can send the pipeline back to docs. The second runs after
   testing and arch-review have approved the work. It analyses the
   architecture and the code the run produced. Both reviews build and use a
   STRIDE threat model kept in the docs site, check code against OWASP
   guidance, run on Opus, and present every finding to the operator, who
   decides what happens to it.

   Motivation: in run 8bdf8823 (FEAT-OPERATOR-EDU) arch-review found that the
   learn server accepted cross-site requests that could start paid
   ``claude -p`` runs. A design-time review would have caught this in the
   spec.

Requirements
------------

.. req:: Design-time security review runs after docs approval, before plan
   :id: REQ-SECURITY-REVIEW-001
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Security flaws found in the design cost a docs edit. Found
       after implementation, they cost code, tests and a fix loop.
   :acceptance: Given an SDD run whose docs the operator has just approved,
       when the orchestrator advances, then the epic moves to
       ``phase=security-design`` and the security agent runs before the plan
       phase. It reads the feature spec, the docs changed in this run
       (``git diff`` of ``docs/source`` since the run's first commit), the
       ADRs, and the existing threat model. For each new or changed C4
       container and each trust boundary it touches, it produces STRIDE
       threats with a proposed mitigation. The plan phase does not start
       until the gate in REQ-SECURITY-REVIEW-002 is passed.
   :non_goal: Does not read or review code. Does not run scanners or audit
       dependencies (ADR-005).
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall add a ``security-design`` phase between docs approval
   and plan, in which an Opus security agent produces a STRIDE threat
   analysis of the proposed changes.

.. req:: Operator decides every design-time finding; reset to docs on request
   :id: REQ-SECURITY-REVIEW-002
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: The operator owns the trade-off between risk and scope. No
       severity threshold triggers an automatic reset.
   :acceptance: Given design-time findings, when the gate is shown, then
       each finding lists severity, STRIDE category, affected C4 element and
       proposed mitigation, and the operator picks one of: "add requirement"
       (reset to docs), "accept risk" (needs a written rationale), or "note".
       If any finding is marked "add requirement", the epic returns to
       ``phase=docs``, ``reset-count`` is incremented, and the docs skill
       receives those findings as the first new requirements to capture.
       After the docs are approved again, the design-time review runs again.
       With no "add requirement" choices, the pipeline advances to plan.
   :non_goal: No automatic reset based on severity.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall present every design-time finding to the operator at a
   gate and reset the pipeline to docs only for findings the operator turns
   into requirements.

.. req:: Threat model and accepted risks persisted in the docs site
   :id: REQ-SECURITY-REVIEW-003
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Each review should build on earlier ones. Accepted risks must
       be visible and traceable, not lost in a terminal session.
   :acceptance: Given a design-time or post-implementation review, when it
       completes, then ``docs/source/security/threat-model/<container>.rst``
       exists for every container it analysed, listing threats as
       ``.. threat::`` needs (id ``THREAT-<CONTAINER>-NNN``, fields
       ``stride``, ``c4_scope``, ``status`` open|mitigated|accepted,
       ``mitigation``, ``links`` to the REQ that mitigates it). Every risk the
       operator accepted is a ``.. risk::`` need (id ``RISK-NNN``) with the
       rationale, the run id, and links to its threat. The Sphinx build
       passes and both pages appear under a "Security" section. The epic
       notes carry a ``[security]`` DSL result for each review.
   :non_goal: No external security tooling integration. No sharing of
       threat models across repositories.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall store the STRIDE threat model and accepted risks as
   sphinx-needs items in ``docs/source/security/`` and record a
   ``[security]`` result block on the epic for each review.

.. req:: Post-implementation security review after arch-review approval
   :id: REQ-SECURITY-REVIEW-004
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Code can drift from a sound design. Mitigations promised in
       the spec must actually be implemented and tested.
   :acceptance: Given arch-review approved by the operator, when the
       orchestrator advances, then the epic moves to
       ``phase=security-review`` and the security agent analyses the run's
       code (``git diff`` of the run's commits) against OWASP ASVS / Top 10
       concerns: input handling, authentication and authorisation,
       injection, secrets, path handling, SSRF and CSRF, unsafe
       deserialisation, and logging of sensitive data. For every threat in
       the threat model linked to this feature, it checks that the
       mitigation exists in code and is covered by a test that fails without
       it, and sets the threat ``status`` accordingly. The epic closes only
       after the gate in REQ-SECURITY-REVIEW-005 is passed.
   :non_goal: No penetration testing or running the system against live
       services. No scanners (ADR-005).
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall add a ``security-review`` phase after arch-review in
   which an Opus security agent checks the run's code against OWASP
   guidance and verifies each threat mitigation.

.. req:: Operator gate and fix loop for post-implementation findings
   :id: REQ-SECURITY-REVIEW-005
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Same ownership as the design gate, with a fix path because
       code exists now.
   :acceptance: Given post-implementation findings, when the gate is shown,
       then for each finding the operator picks "fix" (the orchestrator
       creates a coder bd issue, a worker fixes it with a test, the
       conductor verifies it, and the security review re-runs on the
       affected files), "accept risk" (written rationale, recorded as a
       ``RISK`` need), or "revise docs" (reset to docs). The epic moves to
       ``phase=done`` and closes only when no finding is left open.
   :non_goal: The security agent never edits code itself.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall present post-implementation findings at an operator
   gate offering fix, accept risk, or revise docs, and close the epic only
   when every finding is resolved.

.. req:: Orchestrator, rules and recovery support the two security phases
   :id: REQ-SECURITY-REVIEW-006
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: The phases must survive crashes and resets like every other
       phase, and the rules must say which model runs them.
   :acceptance: Given ``skills/sdd/SKILL.md``, then its pipeline reads docs →
       security-design → plan → implement → arch-review → security-review →
       done, ``/sdd FEAT-XXX`` resumes correctly from either security phase,
       and the 3+ reset escalation counts security-design resets.
       ``skills/rules/RULES.md`` gains a ``security`` row (default opus) in
       Model Selection and the ``[security]`` result format in its DSL
       section. ``skills/security-review/SKILL.md`` exists and states that
       it runs inline in the main context when it must spawn a worker. The
       README pipeline diagram shows both phases. The plugin version is
       bumped.
   :non_goal: No change to the plan, conductor or implement skills beyond
       what the fix loop needs.
   :c4_component: sdd_orchestrator
   :c4_container: sdd_skills

   The system shall extend the orchestrator state machine, the shared rules
   and the README with the two security phases.

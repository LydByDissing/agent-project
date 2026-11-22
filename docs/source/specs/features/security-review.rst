Security Review — Design-Time and Post-Implementation
=====================================================

.. feat:: Security Review — Design-Time and Post-Implementation
   :id: FEAT-SECURITY-REVIEW
   :status: approved

   Adds a security review to the SDD pipeline at two points. The first runs
   right after the operator approves the docs, before planning. It reviews
   the proposed architecture, requirements and skill prompts, where a flaw is
   cheapest to fix, and can send the pipeline back to docs. The second runs
   after testing and arch-review have approved the work. It analyses the
   architecture and the code the run produced. Both reviews build and use a
   STRIDE threat model kept in the docs site, check code against OWASP
   guidance, analyse on Opus, and present every finding to the operator, who
   decides what happens to it.

   The review reads text an attacker may control (code, docs, issue text).
   So the analysis runs in a sub-agent that has only read tools, every gate
   decision is collected interactively and checked by script rather than
   trusted from agent output, the scripts and tests that enforce this are
   protected from workers, and the threat and risk records are append-only.

   Motivation: in run 8bdf8823 (FEAT-OPERATOR-EDU) arch-review found that the
   learn server accepted cross-site requests that could start paid
   ``claude -p`` runs. A design-time review would have caught this in the
   spec. The first manual design-time review of this feature (run 87708f1a)
   found 12 threats in its own design, and two re-reviews found 17 more
   gaps; they are THREAT-SDD-SKILLS-001..017 and each is mitigated by
   requirements below or recorded as noted.

Requirements
------------

.. req:: Design-time security review runs after docs approval, before plan
   :id: REQ-SECURITY-REVIEW-001
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Security flaws found in the design cost a docs edit. Found
       after implementation, they cost code, tests and a fix loop. In this
       plugin, behaviour lives largely in SKILL.md prompts, so those are
       design input too (THREAT-SDD-SKILLS-011).
   :acceptance: Given an SDD run whose docs the operator has just approved,
       when the orchestrator advances, then the epic moves to
       ``phase=security-design`` and the review runs before the plan phase.
       Its input is the feature spec, the ADRs, the existing threat model,
       and the diff of ``docs/source/**`` and ``skills/**/SKILL.md`` from the
       run's base commit (REQ-SECURITY-REVIEW-011) to HEAD. For each new or
       changed C4 container it produces STRIDE threats with a proposed
       mitigation, and for each it lists the container's trust boundaries
       explicitly. The plan phase does not start until the gate in
       REQ-SECURITY-REVIEW-002 is passed.
   :non_goal: Does not review application code. Does not run scanners or
       audit dependencies (ADR-005).
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall add a ``security-design`` phase between docs approval
   and plan, in which a security review produces a STRIDE threat analysis of
   the proposed docs and skill-prompt changes.

.. req:: Operator decides every design-time finding; reset to docs on request
   :id: REQ-SECURITY-REVIEW-002
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: The operator owns the trade-off between risk and scope. No
       severity threshold triggers an automatic reset.
   :acceptance: Given design-time findings, when the gate is shown, then
       decisions are collected per REQ-SECURITY-REVIEW-008 and every open
       THREAT for the feature is listed with severity, STRIDE
       category, C4 element and proposed mitigation, and the operator picks
       one of: "add requirement" (status stays ``open``, reset to docs),
       "accept risk" (status ``accepted``, a RISK need with the operator's
       rationale), or "note" (status ``noted``: known, deliberately left
       unmitigated, no RISK need, does not block closing). If any finding is
       "add requirement", the epic returns to ``phase=docs``, ``reset-count``
       is incremented, and the docs skill receives those findings as the
       first new requirements to capture. After the docs are approved again,
       the design-time review runs again (incrementally, see
       REQ-SECURITY-REVIEW-012). With no "add requirement" choices, the
       pipeline advances to plan.
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
   :acceptance: Given a review, when it completes, then
       ``docs/source/security/threat-model/<container>.rst`` exists for every
       container it analysed, with a "Trust boundaries" list and ``threat``
       needs. Threat ids are ``THREAT-<CONTAINER>-NNN`` where ``<CONTAINER>``
       is the C4 container id upper-cased with ``_`` replaced by ``-`` (e.g.
       ``sdd_skills`` → ``SDD-SKILLS``). Each threat has ``stride``,
       ``c4_scope``, ``status`` (open | noted | accepted | mitigated),
       ``mitigation``, and ``links`` to the REQ that mitigates it. Every
       accepted risk is a ``risk`` need (``RISK-NNN``) in
       ``accepted-risks.rst`` with the operator's rationale, the run id and
       a link to its threat. Decisions on a threat are an append-only list,
       one entry per run (never an overwritten field). Each review also adds
       a review record to ``docs/source/security/reviews.rst``
       (REQ-SECURITY-REVIEW-008). The epic notes carry a ``[security]``
       result for each review; it is advisory, and a mismatch with the docs
       only triggers a re-check. The Sphinx build passes and the pages
       appear under "Security".
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
       the spec must actually be implemented and tested, and an agent's claim
       that they are is not evidence (THREAT-SDD-SKILLS-006).
   :acceptance: Given arch-review approved by the operator, when the
       orchestrator advances, then the epic moves to
       ``phase=security-review`` and the review analyses the run's code
       (diff from the base commit) against OWASP ASVS / Top 10 concerns:
       input handling, authentication and authorisation, injection, secrets,
       path handling, SSRF and CSRF, unsafe deserialisation, and logging of
       sensitive data. For each open threat linked to the feature it may
       propose ``mitigated``, but only with evidence recorded on the threat:
       the mitigation's file:line, the covering test id, and a sabotage check
       run by the orchestrator in a throwaway git worktree (disable the
       mitigation, confirm the test fails), after which ``git status`` of the
       real working tree must be clean. The disabling patch is recorded on
       the threat as evidence. Without that evidence the status stays
       ``open``. Every
       proposed move to ``mitigated`` is shown at the gate in
       REQ-SECURITY-REVIEW-005 for the operator to confirm. The epic closes
       only after that gate is passed.
   :non_goal: No penetration testing or running the system against live
       services. No scanners (ADR-005).
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall add a ``security-review`` phase after arch-review in
   which the review checks the run's code against OWASP guidance and proposes
   threat mitigations only with orchestrator-verified evidence.

.. req:: Operator gate and bounded fix loop for post-implementation findings
   :id: REQ-SECURITY-REVIEW-005
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Same ownership as the design gate, with a fix path because
       code exists now. The fix worker's brief comes from finding text and
       must not be able to weaken the system it fixes
       (THREAT-SDD-SKILLS-010).
   :acceptance: Given post-implementation findings, when the gate is shown,
       then for each finding and each proposed ``mitigated`` the operator
       picks "fix", "accept risk", "note" or "revise docs" (reset to docs),
       or confirms/rejects the mitigation, through the interactive decision
       flow of REQ-SECURITY-REVIEW-008. On "fix", the orchestrator creates a
       coder bd issue whose ``[out]`` paths are only the files named in the
       finding plus one new test file, and never any path in the protected
       set (REQ-SECURITY-REVIEW-006), whatever the finding names. After the worker returns, the
       orchestrator itself runs the full test suites, checks the diff stays
       in scope, and runs a sabotage check that the new test fails without
       the fix. The re-review then covers the whole run diff for the linked
       threats. The post-implementation check fails on any threat linked to
       the feature whose status is ``open``, whatever decisions it carries.
       The epic moves to ``phase=done`` and closes only when every finding is
       ``mitigated``, ``accepted`` or ``noted``.
   :non_goal: The security review never edits code itself, except the
       temporary edit of a sabotage check inside a throwaway worktree.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall present post-implementation findings at an operator
   gate offering fix, accept risk, note or revise docs, run fixes in a
   scope-limited worker verified by the orchestrator, and close the epic
   only when every finding is resolved.

.. req:: Orchestrator enforces the security phases; they cannot be skipped
   :id: REQ-SECURITY-REVIEW-006
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Today arch-review closes the epic itself and ``phase=``
       labels only accumulate, so a security phase could be skipped by
       ordering or by any agent adding a label (THREAT-SDD-SKILLS-002).
   :acceptance: Given ``skills/sdd/SKILL.md``, then its pipeline reads docs →
       security-design → plan → implement → arch-review → security-review →
       done. Every phase change removes the previous ``phase=`` label so the
       epic always has exactly one. arch-review no longer closes the epic or
       marks requirements implemented; only passing the security-review gate
       does. Immediately before every move to plan, every move to done and
       every ``bd close`` of the epic, in a live session and on
       ``/sdd FEAT-XXX`` resume alike, the orchestrator runs the gate check
       (REQ-SECURITY-REVIEW-008) for that stage; if it fails, the move is
       refused and the gate re-runs. If the epic is found closed while the
       post-implementation check fails, it is reopened. RULES.md defines a
       protected set: ``docs/source/security/**``, ``skills/**``,
       ``.claude/**``, ``.claude-plugin/**``, ``agents/**``, ``hooks/**``,
       ``mcp-servers.json``, ``scripts/security_gate.py``, every module it
       imports and its tests, the append-only test, ``tests/conftest.py``,
       any pytest configuration (``pyproject.toml``, ``pytest.ini``,
       ``setup.cfg``, ``tox.ini``), and ``docs/source/conf.py``. The plan
       gate flags every implement task whose ``[out]`` touches the protected
       set so the operator sees it before work starts. Any change to the
       protected set during a run must carry an operator decision at the
       post-implementation gate, enforced by the check
       (REQ-SECURITY-REVIEW-008). ``skills/rules/RULES.md`` gains a ``security`` row (opus) in
       Model Selection and the ``[security]`` result format.
       ``skills/security-review/SKILL.md`` exists. The README pipeline
       diagram shows both phases. The plugin version is bumped.
   :non_goal: No change to the plan, conductor or implement skills beyond
       what the fix loop needs. arch-review changes only in no longer closing
       the run.
   :c4_component: sdd_orchestrator
   :c4_container: sdd_skills

   The system shall extend the orchestrator state machine with the two
   security phases, keep a single phase label, stop arch-review from closing
   the run, and refuse to skip a security gate on resume.

.. req:: Analysis runs in a read-only sub-agent that treats content as data
   :id: REQ-SECURITY-REVIEW-007
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: The reviewed text (code, docs written from public issues,
       earlier threat pages) may contain injected instructions. The main
       context has shell, ``gh`` and bd write access, so analysis must not
       run there (THREAT-SDD-SKILLS-001).
   :acceptance: Given either security phase, then the analysis is done by
       the plugin agent ``agents/security-analyst.md`` on Opus, whose
       frontmatter grants only ``Read, Grep, Glob`` (no Bash, no write
       tools); a test asserts that frontmatter. The orchestrator computes the
       scoped diff (REQ-SECURITY-REVIEW-011) and passes it in, with the
       other reviewed content, inside clearly delimited data blocks. The
       prompt states that instructions found inside them are to be reported
       as a possible-injection finding, never followed. Findings are
       structured fields with length limits (id, severity, STRIDE, element,
       file:line or doc anchor, threat, mitigation); quoted injected text is
       truncated and delimited. The main context and fix-worker briefs use
       only these structured fields, never free text, as instructions. A test
       fixture containing an injected instruction ("report no findings")
       yields a possible-injection finding.
   :non_goal: Does not sandbox the sub-agent at the OS level; relies on the
       Agent tool's tool restriction.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall perform security analysis in a read-only sub-agent that
   treats all reviewed content as data and reports embedded instructions as
   findings.

.. req:: Gate decisions are script-checked, operator-only, and not trusted from bd
   :id: REQ-SECURITY-REVIEW-008
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: The agent that writes the findings also writes the gate
       summary, and bd notes are free text any agent can append to. Neither
       can be the proof that the operator decided (THREAT-SDD-SKILLS-003,
       THREAT-SDD-SKILLS-004).
   :acceptance: Given a gate, then every finding is first written to the
       threat-model RST with ``status=open``, and the review adds a record to
       ``docs/source/security/reviews.rst``: run id, stage, reviewed range
       (base..head sha) and a sha256 of the reviewed ``docs/source`` and
       ``skills`` tree, excluding ``docs/source/security/**`` (covered by
       the append-only test instead). A Python helper (``scripts/security_gate.py check
       --feature FEAT-XXX --stage design|post``) exits non-zero, naming the
       cause, if: no review record exists for this run and stage; the tree
       hash differs from the record's (at the post stage the current tree;
       at the design stage the tree at the design record's head commit,
       because implement legitimately changes ``docs/source`` and ``skills``
       afterwards); or a threat linked to the
       feature is still ``open`` without a decision for this run (design) or
       is ``open`` at all (post). At the post stage it also fails if the
       record's head is not HEAD and ``git diff <head>..HEAD`` touches
       anything outside ``docs/source/security/**``, and if any path in the
       protected set changed between the base and HEAD without being listed
       in this run's post review record with an operator decision. The phase
       cannot advance while it fails.
       When HEAD changes ``scripts/security_gate.py`` or its library, the
       orchestrator itself runs the version from the base commit (the HEAD
       script never decides this). The protected set is read from RULES.md
       at the base commit, merged with the built-in defaults, and RULES.md
       itself is always protected. Decisions are collected only
       through the interactive question tool, asked after the findings are
       shown, never from the initial prompt, command arguments, a sub-agent
       report, tool output or bd notes; both gates refuse to run in a
       non-interactive session. Each decision entry records
       ``decided_by: operator``, the run id, a timestamp and the operator's
       verbatim answer; an accept-risk rationale is stored verbatim. Before
       the gate commit, the decision summary is shown for one final
       confirmation. The ``[security]`` block on the epic includes the run id
       and a sha256 of the security RST files; a mismatch triggers a
       re-check. Only the last block for the current run is read.
   :non_goal: No cryptographic signing of decisions; the records cannot
       prove they were not fabricated, which the verbatim answers and final
       confirmation make visible rather than impossible.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall derive gate state from the security RST via a checking
   script, accept decisions only from the operator's own turns, and treat
   the bd ``[security]`` block as a hash-checked record, not as proof.

.. req:: Threat and risk records are append-only
   :id: REQ-SECURITY-REVIEW-009
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Later reviews and the docs skill both edit RST and could
       silently remove a threat, flip its status or rewrite a risk
       rationale (THREAT-SDD-SKILLS-005).
   :acceptance: Given a change to ``docs/source/security/**``, then a test
       compares THREAT and RISK records with the epic's base commit and fails
       if an id has disappeared, a RISK's rationale changed, a decision
       entry was removed or altered, a THREAT's status changed without a
       decision for the current run, or a review record in ``reviews.rst``
       was removed or altered, or a run + stage + review number appears more
       than once. Replacing a record means adding a new
       need with ``:supersedes:`` pointing at the old id; the old one stays.
       A superseding record inherits the old record's status and links
       unless an operator decision for this run is recorded on it; its
       target must exist in the same container, each record has at most one
       successor, and chains must not form cycles. The orchestrator runs this
       test before every gate commit (the repository has no CI). The
       security docs are committed at each gate with the decisions in the
       commit message.
   :non_goal: Does not prevent edits; makes them visible and blocks the
       gate commit.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall keep THREAT and RISK records append-only, enforced by a
   test against the base branch.

.. req:: Secrets and exploit detail are never published
   :id: REQ-SECURITY-REVIEW-010
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: The post-implementation review looks for secrets, and the
       natural way to report one would copy it into docs, bd notes or a
       GitHub comment, all of which get pushed (THREAT-SDD-SKILLS-007).
   :acceptance: Given findings, then a secret is named by file:line and
       type, never by value. Before any commit, ``scripts/security_gate.py
       redact-check`` scans ``docs/source/security/**``, the run's design
       log, the gate commit message, the ``[security]`` block and every bd
       text the security flow writes (the epic block and fix issues) for
       likely credentials (known key prefixes, private-key headers,
       high-entropy tokens) and fails naming the location. 40- and
       64-character hex values in known sha fields are allowed. Fixture
       tests: a planted AWS access key and a PEM header fail; a sha256 field
       passes. Open threats in the RST describe impact and fix, not
       step-by-step exploitation. Security findings are never posted to
       GitHub by the GitHub Bridge.
   :non_goal: This output guard is not a code scanner; ADR-005's "no
       scanners" applies to reviewing code, not to guarding the review's own
       output.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall keep secret values and exploit steps out of every
   security output and guard that with a pre-commit check.

.. req:: Review input is scoped, budgeted and anchored to a base commit
   :id: REQ-SECURITY-REVIEW-011
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Raw diffs include generated, binary, lock and vendored files
       (run 87708f1a's docs diff was 182 KB, mostly one SVG), which wastes
       Opus spend and can silently exceed the context. "Since the run
       started" needs a fixed reference (THREAT-SDD-SKILLS-009,
       THREAT-SDD-SKILLS-011).
   :acceptance: Given a new epic, then the orchestrator proposes the fork
       point (HEAD at creation, which on a stacked branch is not the
       merge-base with main) and the operator confirms it. The base is stored
       in the run's first committed review record in ``reviews.rst``
       (append-only), and ``base=<sha>`` on the epic only mirrors it. Resets
       do not change it. ``security_gate.py`` fails unless the epic has
       exactly one ``base=`` label equal to the recorded base, the base is an
       ancestor of HEAD, and ``git merge-base <main> HEAD`` is an ancestor of
       the base (or equal to it). After a rebase the base may be re-recorded
       only through an operator decision entry. Review
       input excludes generated, binary, lockfile and vendored paths (default
       list in RULES.md, extendable per project) and has a size budget. If
       the in-scope input exceeds the budget, the excluded part is listed at
       the gate as "not reviewed", never silently truncated. The
       ``[security]`` block records the input size and token use.
   :non_goal: No automatic summarisation of oversized diffs.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall anchor review input to a recorded base commit, exclude
   generated and vendored content, enforce a size budget, and report any
   unreviewed scope at the gate.

.. req:: Re-reviews are incremental and loops are bounded
   :id: REQ-SECURITY-REVIEW-012
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Each re-review is a fresh, non-deterministic Opus run that can
       reword or add findings, and neither the reset loop nor the fix loop
       has a limit (THREAT-SDD-SKILLS-008).
   :acceptance: Given a re-review after a reset or a fix, then it covers
       input changed since the last review (the head sha of the latest
       committed review record, never a bd value) plus threats still
       ``open``, and always re-reads the full current spec; findings already ``noted`` or ``accepted`` are not raised
       again unless their C4 element changed. After 2 security-design resets
       in one run, or 3 fix iterations, the orchestrator pauses and asks the
       operator whether to continue; without an explicit yes it stops.
   :non_goal: No cap on the number of findings per review.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall make security re-reviews incremental and require
   operator confirmation to continue past the reset and fix-loop limits.

.. req:: Findings are validated before the gate
   :id: REQ-SECURITY-REVIEW-013
   :links: FEAT-SECURITY-REVIEW
   :status: approved
   :rationale: Made-up C4 ids or broken REQ links would enter published
       needs and mislead later reviews (THREAT-SDD-SKILLS-012).
   :acceptance: Given the analysis sub-agent's findings, then
       ``scripts/security_gate.py validate`` checks severity
       (crit|high|med|low), STRIDE letter (S|T|R|I|D|E), that each C4 id
       exists in the architecture docs, and that each REQ/THREAT link
       resolves and belongs to the feature under review; invalid findings are returned to the sub-agent once for
       correction and otherwise shown at the gate as invalid. The Sphinx
       build treats warnings in ``docs/source/security/**`` as errors.
   :non_goal: Does not judge whether a finding is correct, only well-formed.
   :c4_component: security_review
   :c4_container: sdd_skills

   The system shall validate the form and references of every finding
   before it reaches the gate or the docs.

SDD Skills — Threat Model
=========================

Container: ``sdd_skills``. Threats recorded by the design-time security
review of FEAT-SECURITY-REVIEW (run 87708f1a, 2026-11-22): 001..012 from the
first review, 013..014 from review 2, 015..017 from review 3, 018..021 from
the narrow check after reset 3. 001..014 are
``open`` until the linked requirements are implemented and verified;
015..021 are ``noted`` by the operator and handled during implementation.

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

.. threat:: Run-created records unprotected by base-only comparison
   :id: THREAT-SDD-SKILLS-018
   :status: noted
   :stride: T
   :c4_scope: security_review
   :decided_by: operator
   :run: 87708f1a
   :mitigation: Plan acceptance check: also compare with the latest gate commit, and read the base from the git commit that first added the run's first review record.
   :links: REQ-SECURITY-REVIEW-009, REQ-SECURITY-REVIEW-011

   The append-only test compares only with the base commit, so review records, this run's decisions, this feature's threats and the stored base, all created during the run, can be altered between gates. Noted 2026-11-22 (narrow check, SD4-01) under the operator's policy for this step.

.. threat:: Forged edits hidden in legitimate protected-path changes
   :id: THREAT-SDD-SKILLS-019
   :status: noted
   :stride: T
   :c4_scope: security_review
   :decided_by: operator
   :run: 87708f1a
   :mitigation: Plan acceptance check: measure implement-phase protected changes from the last design record's head; list records added since; accept only the record added by the post gate's own commit.
   :links: REQ-SECURITY-REVIEW-008

   Path-level base..HEAD comparison cannot separate forged additions from expected changes to protected paths; a worker can add its own post review record. Noted 2026-11-22 (narrow check, SD4-02) under the operator's policy for this step.

.. threat:: Post check fails on legitimate bd and design-log commits
   :id: THREAT-SDD-SKILLS-020
   :status: noted
   :stride: D
   :c4_scope: security_review
   :decided_by: operator
   :run: 87708f1a
   :mitigation: Implementation: allow .beads/** and the run's design log in the head..HEAD rule; exclude the design log from the hash or hash at gate-commit time.
   :links: REQ-SECURITY-REVIEW-008

   Tracked .beads/** commits and the run's design log written after the hash make the post head rule and tree hash fail, pushing the operator toward a bypass. Noted 2026-11-22 (narrow check, SD4-03) under the operator's policy for this step.

.. threat:: Base record and import scope wording untestable
   :id: THREAT-SDD-SKILLS-021
   :status: noted
   :stride: T
   :c4_scope: security_review
   :decided_by: operator
   :run: 87708f1a
   :mitigation: Implementation: base field on each review record; effective base is the latest operator-decided re-record, else the first; imports means repository modules.
   :links: REQ-SECURITY-REVIEW-011, REQ-SECURITY-REVIEW-006

   The base sits in prose, not a record field; the effective base after a re-record is undefined; 'modules it imports' is unscoped. Noted 2026-11-22 (narrow check, SD4-04) under the operator's policy for this step.

.. threat:: Unguarded shell variables empty the review scope
   :id: THREAT-SDD-SKILLS-022
   :status: open
   :stride: T/I
   :c4_scope: security_review
   :severity: high
   :mitigation: Re-set and guard variables in the same call (${BASE:?}, git rev-parse --verify "${BASE}^{commit}", set -u), brace every "${BASE}:path", and stop the review if the scoped diff is empty while the run changed files.
   :links: REQ-SECURITY-REVIEW-011, REQ-SECURITY-REVIEW-001, REQ-SECURITY-REVIEW-004, THREAT-SDD-SKILLS-009, THREAT-SDD-SKILLS-014

   Shell variables do not persist between Bash calls and zsh reads "$BASE:s..." as a history modifier. An empty or mangled BASE turns "$BASE"..HEAD into an empty diff (no findings, no error) and "$BASE:path" into an index lookup, so the bootstrap check prints present when the script is absent (observed live in run 87708f1a). Anchor: ``skills/security-review/SKILL.md:157``. Post-implementation review 1 of run 87708f1a (SP-01).

.. threat:: HEAD script still decides the base run
   :id: THREAT-SDD-SKILLS-023
   :status: open
   :stride: T/E
   :c4_scope: security_review
   :severity: high
   :mitigation: The orchestrator decides with plain git (git diff --name-only BASE HEAD -- scripts/security_gate*.py) and, when anything differs, runs only the base worktree copy with python3 -I, never the HEAD script first.
   :links: REQ-SECURITY-REVIEW-008, REQ-SECURITY-REVIEW-006, THREAT-SDD-SKILLS-013

   The HEAD copy still decides whether the base version runs: cmd_check calls script_state and base-path is itself HEAD code, so a worker that alters the HEAD script or lib can report same and skip the base run. Anchor: ``scripts/security_gate.py:45``. Post-implementation review 1 of run 87708f1a (SP-02).

.. threat:: Decision entries lack stage and target status
   :id: THREAT-SDD-SKILLS-024
   :status: open
   :stride: T/R
   :c4_scope: security_review
   :severity: high
   :mitigation: Record stage= and the target status in each decision entry and allow a status change only with a matching entry for this run, stage and new status added after the compared record.
   :links: REQ-SECURITY-REVIEW-009, REQ-SECURITY-REVIEW-008, THREAT-SDD-SKILLS-005, THREAT-SDD-SKILLS-003

   Any operator entry for the run id authorises a status change; entries carry no stage or target status, so a design-stage add-requirement entry lets an agent later flip the threat to mitigated or noted at post with append-only and check both passing. Anchor: ``scripts/security_gate_lib.py:609``. Post-implementation review 1 of run 87708f1a (SP-03).

.. threat:: Sabotage check accepts any non-zero exit
   :id: THREAT-SDD-SKILLS-025
   :status: open
   :stride: T
   :c4_scope: security_review
   :severity: high
   :mitigation: Commit or copy the fix first, verify the edit applied (non-empty diff), require the test to pass unsabotaged and to fail with exit 1 naming that test when sabotaged, define SCRATCH, use set -e.
   :links: REQ-SECURITY-REVIEW-004, REQ-SECURITY-REVIEW-005, THREAT-SDD-SKILLS-006, THREAT-SDD-SKILLS-010

   The sabotage check accepts any non-zero exit (failed cd or edit, pytest exit 4 or 5, missing test), the worktree from HEAD lacks uncommitted fixes and tests, and SCRATCH is never set, so fake evidence can pass for mitigated and for fix verification. Anchor: ``skills/security-review/SKILL.md:411``. Post-implementation review 1 of run 87708f1a (SP-04).

.. threat:: Guessable DATA terminator breaks the data boundary
   :id: THREAT-SDD-SKILLS-026
   :status: open
   :stride: E/T
   :c4_scope: security_review
   :severity: high
   :mitigation: Use a random per-run nonce in opening and closing markers, reject or escape content containing it, tell the analyst only the nonce terminator counts, and add a fixture test with an embedded DATA>>>.
   :links: REQ-SECURITY-REVIEW-007, THREAT-SDD-SKILLS-001

   DATA blocks end with a fixed, guessable DATA>>> marker with no escaping, so reviewed content containing that literal closes the block early and the rest lands in the instruction part of the analyst prompt. Anchor: ``skills/security-review/SKILL.md:227``. Post-implementation review 1 of run 87708f1a (SP-05).

.. threat:: Design log and fix issues escape redact-check
   :id: THREAT-SDD-SKILLS-027
   :status: open
   :stride: I
   :c4_scope: security_review
   :severity: med
   :mitigation: Always include the design-log glob when --feature and --run are given, pass each fix-issue text via --text-file before bd create, and add a fixture test with a planted key in the design log.
   :links: REQ-SECURITY-REVIEW-010, THREAT-SDD-SKILLS-007

   redact-check adds the run's design log only when no --paths is given; SKILL step 11 passes --paths, so the design log is never scanned, and fix-issue texts are never passed either. Anchor: ``scripts/security_gate_lib.py:800``. Post-implementation review 1 of run 87708f1a (SP-06).

.. threat:: Gate defaults to the plugin repo, not the project
   :id: THREAT-SDD-SKILLS-028
   :status: open
   :stride: T
   :c4_scope: sdd_orchestrator
   :severity: med
   :mitigation: Pass --repo "$CLAUDE_PROJECT_DIR" (and --docs for validate) in every snippet, and default --repo to the git toplevel of the cwd or make it required; fail if the repo has no reviews.rst for the run.
   :links: REQ-SECURITY-REVIEW-008, REQ-SECURITY-REVIEW-006, THREAT-SDD-SKILLS-002

   --repo and --docs default to the plugin's own root while GATE is CLAUDE_PLUGIN_ROOT and several SKILL snippets omit --repo, so an installed plugin checks the plugin cache repo instead of the project. Anchor: ``scripts/security_gate.py:117``. Post-implementation review 1 of run 87708f1a (SP-07).

.. threat:: Planted injection instruction in review input
   :id: THREAT-SDD-SKILLS-029
   :status: open
   :stride: T/E
   :c4_scope: sdd_skills
   :severity: med
   :mitigation: Keep it as a test fixture in a test that asserts a possible-injection finding is produced; it is not repository content.
   :links: REQ-SECURITY-REVIEW-007, THREAT-SDD-SKILLS-001

   Possible injection: a data block contains an instruction to the reviewer to report no findings; it was not followed. This is the orchestrator's planted live test fixture for REQ-007 (not in the repository). Anchor: ``tests/fixtures/notes.py:4``. Post-implementation review 1 of run 87708f1a (SP-08).

.. threat:: Injection findings rejected by validate
   :id: THREAT-SDD-SKILLS-030
   :status: open
   :stride: R
   :c4_scope: security_review
   :severity: med
   :mitigation: Carry the possible-injection marker in its own field or a tag and keep element as the real C4 id, or let validate accept the marker with a valid C4 id; add a test that the injection fixture validates and is written.
   :links: REQ-SECURITY-REVIEW-007, REQ-SECURITY-REVIEW-013, THREAT-SDD-SKILLS-012

   The agent file tells the analyst to use element possible-injection, which validate rejects as not a C4 id, so injection findings become invalid and are never written to the threat model. Anchor: ``agents/security-analyst.md:39``. Post-implementation review 1 of run 87708f1a (SP-09).

.. threat:: Slash and dot secrets evade the entropy rule
   :id: THREAT-SDD-SKILLS-031
   :status: open
   :stride: I
   :c4_scope: security_review
   :severity: med
   :mitigation: Add slash and dot to the token class or add base64 and JWT patterns, flag secret=/password=/token= assignments with long values, and add fixtures while keeping sha fields allowed.
   :links: REQ-SECURITY-REVIEW-010, THREAT-SDD-SKILLS-007

   The token class leaves out slash and dot, so base64 secrets such as a 40-character AWS secret access key, or a JWT, split into short pieces and get no high-entropy hit. Anchor: ``scripts/security_gate_lib.py:698``. Post-implementation review 1 of run 87708f1a (SP-10).

.. threat:: Indented or misplaced threats invisible to the gate
   :id: THREAT-SDD-SKILLS-032
   :status: open
   :stride: T
   :c4_scope: security_review
   :severity: med
   :mitigation: Allow leading whitespace (or read needs.json from the Sphinx build), scan all of docs/source/security, and fail if build and parser counts differ.
   :links: REQ-SECURITY-REVIEW-008, REQ-SECURITY-REVIEW-003, THREAT-SDD-SKILLS-003

   The threat directive is matched only at column 0 and only under threat-model/, so an indented threat or one elsewhere under security/ still renders as open but is invisible to the post check. Anchor: ``scripts/security_gate_lib.py:26``. Post-implementation review 1 of run 87708f1a (SP-11).

.. threat:: Security block hash fragile and format mismatched
   :id: THREAT-SDD-SKILLS-033
   :status: open
   :stride: S/R
   :c4_scope: security_review
   :severity: low
   :mitigation: Compute the hash with a NUL-safe gate subcommand over sorted relative paths, align the RULES.md format with SKILL step 12, and add a doc-contract test that both match.
   :links: REQ-SECURITY-REVIEW-003, REQ-SECURITY-REVIEW-008, THREAT-SDD-SKILLS-004

   The [security] hash uses find|sort|xargs cat, which splits names on whitespace, and the RULES.md [security] format lacks sha256 and input_bytes, so a block written to the RULES format cannot be hash-checked on resume. Anchor: ``skills/security-review/SKILL.md:569``. Post-implementation review 1 of run 87708f1a (SP-12).

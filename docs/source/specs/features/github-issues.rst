GitHub Issue Integration
========================

.. feat:: GitHub Issue Integration
   :id: FEAT-GITHUB-ISSUES
   :status: implemented
   :links:

   Integrates GitHub Issues as the natural-language source of truth for
   features in the SDD pipeline. When a developer invokes ``/sdd #N``, the
   pipeline pulls the GitHub issue body and all comments (with author
   timestamps) as the opening brief for the docs interview, so the developer
   does not re-explain what is already written. As the pipeline progresses,
   structured updates are written back to the GitHub issue: the description
   is enriched after docs approval, a comment is posted on plan approval, the
   issue is closed when the pipeline reaches ``done``, and (if a GitHub
   Projects board is linked) the card is moved to reflect the current phase.

   Beads issues created during planning carry ``--external-ref gh-N`` so
   traceability runs in both directions: GitHub ↔ beads.

Requirements
------------

.. req:: GitHub issue fetch on /sdd #N invocation
   :id: REQ-GITHUB-ISSUES-001
   :links: FEAT-GITHUB-ISSUES
   :status: implemented
   :rationale: Developers write feature intent in GitHub Issues. Re-asking
       the same questions in the docs interview wastes time and risks
       divergence from what is already agreed in the issue thread.
   :acceptance: Given ``/sdd #3``, when the docs interview starts, the
       GitHub Bridge has fetched issue #3 body and all comments with author
       and ISO timestamp, and this content is presented to the Docs Skill
       as a structured brief before the first interview question is asked.
   :non_goal: Does not parse or interpret the GitHub issue body into
       structured fields. It is passed as NL context; the Docs Skill does
       the structuring.
   :c4_component: github_bridge
   :c4_container: sdd_skills

   The system shall, upon ``/sdd #N`` invocation, fetch the GitHub issue
   body and all comments (with author handle and ISO creation timestamp)
   via ``gh issue view N --comments`` and format them as a brief passed to
   the Docs Skill before the interview begins.

.. req:: FEAT-ID derivation and confirmation from GitHub issue title
   :id: REQ-GITHUB-ISSUES-002
   :links: FEAT-GITHUB-ISSUES
   :status: implemented
   :rationale: FEAT-IDs must be stable, meaningful identifiers. Deriving
       from the issue title gives a useful default while letting the
       developer correct it before it is stamped on RST files and bd issues.
   :acceptance: Given issue #3 with title "Link beads issues to GitHub
       issue", the Orchestrator derives ``FEAT-LINK-BEADS-GH`` (or similar
       kebab-slug ≤ 20 chars, all caps after ``FEAT-``), presents it to the
       user, and waits for confirmation or an override before proceeding.
   :non_goal: Does not create a GitHub milestone or tag for the FEAT-ID.
       Does not auto-assign the issue to the current user.
   :c4_component: sdd_orchestrator
   :c4_container: sdd_skills

   The system shall derive a ``FEAT-XXX`` identifier from the GitHub issue
   title (kebab-case, uppercased, maximum 20 characters after ``FEAT-``),
   display it to the developer, and accept a confirmation or override before
   the docs phase begins.

.. req:: bd epic linked to originating GitHub issue
   :id: REQ-GITHUB-ISSUES-003
   :links: FEAT-GITHUB-ISSUES
   :status: implemented
   :rationale: Bidirectional traceability — from the agent DSL world back
       to the human NL world — requires an explicit link at the epic level.
       All bd task issues inherit this link via ``--external-ref`` so any
       task can be traced back to the GitHub issue.
   :acceptance: Given ``/sdd #3``, the bd epic created by the Orchestrator
       has ``external-ref=gh-3``. All bd task issues created by the Plan
       Skill also carry ``--external-ref gh-3``.
   :non_goal: Does not sync labels between GitHub and bd. Does not create
       a GitHub issue if one does not exist.
   :c4_component: sdd_orchestrator
   :c4_container: sdd_skills

   The system shall create the bd epic and all bd task issues with
   ``--external-ref gh-N``, where N is the GitHub issue number, making
   every agent work item traceable to its originating GitHub issue.

.. req:: GitHub issue description updated after docs approval
   :id: REQ-GITHUB-ISSUES-004
   :links: FEAT-GITHUB-ISSUES
   :status: implemented
   :rationale: After the docs phase, the structured spec captures more
       precision than the original NL issue. Reflecting this back into
       the GitHub issue description keeps GitHub as a usable reference even
       for people who do not read the Sphinx docs.
   :acceptance: Given docs approved by the developer, within 30 seconds
       the GitHub issue description has a new ``## SDD Spec`` section
       appended (not replacing existing content) containing: FEAT-ID,
       list of REQ-XXX IDs with one-line summaries, and a link to the
       Sphinx docs page. The section is idempotent — re-running replaces
       the previous ``## SDD Spec`` block rather than appending a duplicate.
   :non_goal: Does not reformat or rewrite the original issue body.
       Does not post a comment — uses a description update.
   :c4_component: github_bridge
   :c4_container: sdd_skills

   The system shall, after the developer approves the docs gate, append a
   structured ``## SDD Spec`` section to the GitHub issue description
   containing the FEAT-ID, all REQ-XXX IDs with one-line summaries, and
   the bd epic ID. If a ``## SDD Spec`` section already exists it is
   replaced in place.

.. req:: GitHub comment posted on plan approval
   :id: REQ-GITHUB-ISSUES-005
   :links: FEAT-GITHUB-ISSUES
   :status: implemented
   :rationale: Plan approval is the commit to start implementation. Posting
       a comment at this moment creates an auditable timestamp on the GitHub
       issue marking when the team moved from design to implementation.
   :acceptance: Given the developer approves the plan gate, within 30
       seconds a new comment appears on the GitHub issue containing: bd epic
       ID, total task count, list of task titles (coder / tester / reviewer),
       and run ID.
   :non_goal: Does not post intermediate comments during implementation.
       Does not post on docs approval (that uses a description update instead).
   :c4_component: github_bridge
   :c4_container: sdd_skills

   The system shall post a comment on the GitHub issue when the plan gate
   is approved, summarising the bd epic ID, run ID, and the list of tasks
   (title + role) that will be executed.

.. req:: GitHub issue closed on pipeline done
   :id: REQ-GITHUB-ISSUES-006
   :links: FEAT-GITHUB-ISSUES
   :status: implemented
   :rationale: GitHub issues represent intent. When the SDD pipeline
       completes (all requirements implemented, arch-review approved), the
       intent has been fulfilled. Closing the issue keeps the GitHub Issues
       list clean and signals completion to the team.
   :acceptance: Given ``phase=done`` reached after arch-review approval,
       the GitHub issue state becomes ``CLOSED`` within 30 seconds.
       If the pipeline resets before reaching done, the issue remains open.
   :non_goal: Does not reopen the issue if a pipeline reset occurs after
       it was closed. Closing is a one-way transition.
   :c4_component: github_bridge
   :c4_container: sdd_skills

   The system shall close the originating GitHub issue when the SDD pipeline
   reaches ``phase=done`` after arch-review approval.

.. req:: GitHub Projects card moved with SDD phase transitions
   :id: REQ-GITHUB-ISSUES-007
   :links: FEAT-GITHUB-ISSUES
   :status: implemented
   :rationale: Teams using GitHub Projects as a Kanban board expect cards
       to reflect actual work state without manual updates.
   :acceptance: Given a GitHub Projects board linked to the repository,
       when plan is approved the card for issue #N moves to a column named
       "In Progress" (or equivalent); when ``phase=done``, it moves to
       "Done" (or equivalent). If no Projects board is linked, the Bridge
       logs a debug note and continues without error.
   :non_goal: Does not create a Projects board or card if none exists.
       Does not manage column configuration or create custom columns.
       Column name matching is case-insensitive and fuzzy (In Progress /
       in_progress / In-Progress all match).
   :c4_component: github_bridge
   :c4_container: sdd_skills

   The system shall move the GitHub Projects card for the source issue from
   its current column to "In Progress" on plan approval, and to "Done" on
   pipeline completion, when a linked Projects board exists. The operation
   is a no-op if no board is linked.

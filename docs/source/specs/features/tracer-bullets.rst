Tracer Bullets — Vertical Slice Planning
=========================================

.. feat:: Tracer Bullets — Vertical Slice Planning
   :id: FEAT-TRACER-BULLETS
   :status: implemented

   Changes the Plan Skill to decompose feature work into tracer bullets:
   thin vertical slices that cross all necessary stack layers for one
   testable behavior, rather than building full horizontal layers one at a
   time. Each slice produces independently testable output the moment its
   coder task closes. Before slices, a prefactor phase scaffolds whatever
   infrastructure, services, or DB setup must exist first — "make the
   change easy, then make the easy change." The DSL wire format gains an
   explicit ``type=prefactor`` task type to distinguish scaffolding work
   from slice work. Concept credited to Matt Pocock and *The Pragmatic
   Programmer* (Thomas & Hunt).

Requirements
------------

.. req:: Explicit prefactor task type in the DSL wire format
   :id: REQ-TRACER-BULLETS-001
   :links: FEAT-TRACER-BULLETS
   :status: implemented
   :rationale: Scaffolding (new services, DB setup, migration framework,
       large refactors) is not a vertical slice — it produces no
       independently testable behavior on its own. Distinguishing it
       explicitly in the DSL lets the conductor sequence it correctly and
       lets arch-review verify it is not being misused as a horizontal
       layer in disguise.
   :acceptance: Given a feature requiring a new DB migration framework
       before any slice can run, the Plan Skill creates a bd issue with
       ``[task id=t0 type=prefactor]`` and a goal describing the
       scaffolding work. All slice coder tasks that depend on it carry
       ``depends=t0`` in the ``[exec]`` block. The existing valid types
       ``code``, ``review``, and ``test`` are unchanged.
   :non_goal: Does not change the coder worker behaviour — a prefactor
       worker reads the same worker prompt as a code worker. The type
       affects DSL semantics and scheduling only, not execution.
   :c4_component: plan_skill
   :c4_container: sdd_skills

   The system shall extend the Task DSL wire format with ``type=prefactor``
   as a valid value alongside ``code``, ``review``, and ``test``. The Plan
   Skill shall create prefactor tasks for any scaffolding, infrastructure
   setup, or large refactor work that must complete before slice tasks can
   begin, and shall wire slice tasks as dependents of their prefactor tasks
   in the ``[exec]`` block.

.. req:: Slice-first decomposition with testable-behavior goals
   :id: REQ-TRACER-BULLETS-002
   :links: FEAT-TRACER-BULLETS
   :status: implemented
   :rationale: When the Plan Skill decomposes by component or layer, the
       first task closed produces a layer artifact, not working behavior.
       Nothing is testable until all layers are done. Decomposing by
       testable behavior means something runs and passes after the first
       coder task closes — regardless of how many slices remain.
   :acceptance: Given a requirement "user can log in", the Plan Skill
       produces at least one slice whose ``[goal]`` is framed as observable
       behavior ("user submits valid credentials and receives a session
       token"), not as a layer deliverable ("implement the user DB model").
       The slice's ``[accept]`` field is a Given/When/Then criterion
       verifiable by running tests immediately after the coder closes,
       without any other slice being complete.
   :non_goal: Does not require every slice to touch every layer of the
       stack — only the layers that behavior needs. A slice may be
       entirely within one layer if that is genuinely the smallest
       cross-cutting unit for that behavior.
   :c4_component: plan_skill
   :c4_container: sdd_skills

   The system shall decompose each requirement into one or more vertical
   slices after identifying prefactor work. Each slice is the smallest
   task whose coder output crosses all layers needed to make one testable
   behavior work end-to-end. The ``[goal]`` of a slice task must describe
   observable behavior, and the ``[accept]`` must be a testable criterion
   that can be validated the moment the slice coder closes.

.. req:: Happy-path slice ordered first
   :id: REQ-TRACER-BULLETS-003
   :links: FEAT-TRACER-BULLETS
   :status: implemented
   :rationale: The happy path is the critical path. Validating it first
       confirms the core approach works before investing in error paths and
       edge cases. If the happy path is broken, later slices may need to
       be reworked.
   :acceptance: Given a feature decomposed into a happy-path slice and one
       or more error/edge-case slices with no file-overlap dependency
       between them, the happy-path coder task appears earlier in the
       ``[exec]`` block than the error/edge-case coder tasks (no
       ``depends=`` required — it is a sequencing preference expressed
       through task ordering in the exec block).
   :non_goal: Does not override a real file-overlap dependency. If an
       error-path slice genuinely shares output files with the happy-path
       slice, the file-overlap rule takes precedence and they are
       sequenced or merged regardless of happy-path preference.
   :c4_component: plan_skill
   :c4_container: sdd_skills

   The system shall order slice tasks so the happy-path (critical-path)
   slice is listed first in the ``[exec]`` block, ahead of error-path and
   edge-case slices that have no dependency on it. The overall task order
   in the exec block is: prefactor tasks → happy-path slice → remaining
   slices in ascending complexity/risk order.

.. req:: File-overlap analysis enforces independent testability
   :id: REQ-TRACER-BULLETS-004
   :links: FEAT-TRACER-BULLETS
   :status: implemented
   :rationale: If two slice tasks write the same file, running the tester
       for the first slice after its coder closes will fail or produce
       misleading results because the second coder has not yet made its
       changes. Shared output files signal that the two "slices" are
       really one slice. The Plan Skill must detect this and either merge
       them or sequence them, so each tester is only ever run against a
       stable, complete file.
   :acceptance: Given two slice coder tasks whose anticipated ``[out]``
       paths share at least one file, the Plan Skill either merges them
       into a single slice task or adds ``depends=<earlier>`` to the later
       task in the ``[exec]`` block — never leaves them unsequenced. Given
       two slice coder tasks with entirely disjoint ``[out]`` paths, they
       have no ``depends=`` relationship between them and each has its own
       independent tester task that can run as soon as its coder closes.
   :non_goal: Does not track actual file changes at runtime — anticipated
       ``[out]`` paths declared at plan time are the only input. Does not
       prevent two tasks from reading the same file; only write overlap is
       analysed.
   :c4_component: plan_skill
   :c4_container: sdd_skills

   The system shall compare the anticipated output paths (``[out]``
   entries) across all slice coder tasks. Any pair that shares at least
   one output path must be either merged into a single slice or explicitly
   sequenced with ``depends=`` in the ``[exec]`` block. Slice tasks with
   entirely disjoint output paths shall have no ``depends=`` between them
   and shall each be paired with an independent tester task.

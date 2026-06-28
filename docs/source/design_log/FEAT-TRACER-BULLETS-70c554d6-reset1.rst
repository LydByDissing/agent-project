FEAT-TRACER-BULLETS Design Session — run 70c554d6 reset 1
==========================================================

:Date: 2026-06-27
:Feature: FEAT-TRACER-BULLETS
:Run: 70c554d6
:Reset: 1
:GitHub Issue: #4
:c4_elements: plan_skill sdd_skills
:Requirements: FEAT-TRACER-BULLETS REQ-TRACER-BULLETS-001 REQ-TRACER-BULLETS-002 REQ-TRACER-BULLETS-003 REQ-TRACER-BULLETS-004

Context
-------

Reset triggered at the arch-review gate after the first implementation pass.
The first pass produced a ``[layers]`` annotation in the Task DSL and a
file-overlap dependency heuristic, but missed the core intent of the feature:
changing the *decomposition unit* from component/requirement groups to
independently testable vertical slices (tracer bullets).

Interview Transcript
--------------------

**Agent**: What does the user experience look like when this feature is
working — what happens differently from plan approval to first testable
output?

**User**: The user experience is the same. This is more about how the
planning work. Instead of building large horizontal layers one at a time,
we need to pivot to a vertical approach where we faster and more easily
can start firing our unit tests. So instead of first building the full DB
layers, we handle the full vertical stack needed to just handle the
vertical slice we need to implement the requested feature, or even better
sub-features when task complexity rises.

**Agent**: What does Matt Pocock specifically say about tracer bullets — the
source cited in the GitHub issue?

**Research**: Matt Pocock's definition (verbatim): "Tracer bullet is a
magic word to make the AI only do the smallest possible task which crosses
all layers." His ``to-issues`` skill adds a prefactoring phase — "Make the
change easy, then make the easy change" — where scaffolding and
infrastructure work is identified as blocker issues before slices begin.
Each slice must be demoable/verifiable on its own.

**Agent**: Earlier you mentioned scaffolding and large refactors can't fit
in a single slice task. How does that map to this approach?

**User**: Usually early on in the project we need to scaffold a whole lot
of work, services, infrastructure etc. This can't be done within a single
task. Same goes for larger refactors.

**Agent**: Should the Plan Skill label these explicitly as prefactor vs
slice in the DSL?

**User**: Yes, make it explicit.

**Agent**: Should the first-pass ``[layers]`` annotation be kept, removed,
or rephrased?

**User**: No overlap. Remove what is wrong, rephrase where applicable.

Key Decisions
-------------

- Decomposition unit is *testable behavior* (slice), not component or layer.
- ``type=prefactor`` added to Task DSL for scaffolding/infrastructure work.
- ``[layers]`` annotation removed entirely — wrong direction.
- File-overlap analysis retained and rephrased: shared output files signal
  the two tasks are really one slice (must merge or sequence).
- Slice ordering: prefactors first, then happy-path slice, then remaining
  slices by complexity.
- Source authority: Matt Pocock's tracer-bullet definition + *The Pragmatic
  Programmer* (Thomas & Hunt).

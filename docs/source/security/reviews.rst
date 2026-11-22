Security Reviews
================

One record per security review: run, stage, reviewed range and a hash of the
reviewed tree. ``scripts/security_gate.py`` requires a matching record before
a phase can advance (REQ-SECURITY-REVIEW-008). Records before that script
exists were made by hand and carry no tree hash.

Run 87708f1a base: ``a429fd8``, confirmed by the operator 2026-11-22 (HEAD when the epic was created; stacked on
FEAT-OPERATOR-EDU, so not the merge-base with main).

.. list-table::
   :header-rows: 1

   * - Run
     - Stage
     - Review
     - Range
     - Findings
     - Outcome
   * - 87708f1a
     - design
     - 1
     - a429fd8..caef6ed
     - 12 (SD-01..12)
     - all added as requirements; reset 1
   * - 87708f1a
     - design
     - 2 (incremental)
     - caef6ed..d076b52
     - 10 (SD2-01..10)
     - all added as requirements; reset 2
   * - 87708f1a
     - design
     - 3 (incremental)
     - d076b52..9c75ae6
     - 7 (SD3-01..07)
     - 01, 02 added, 03, 05 folded in; reset 3; 04, 06, 07 noted
   * - 87708f1a
     - design
     - 4 (narrow)
     - 9c75ae6..24fc00a
     - 4 (SD4-01..04)
     - SD3-02 closed; all four noted per policy; planning may proceed


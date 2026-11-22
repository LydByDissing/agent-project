Security Reviews
================

One record per security review: run, stage, reviewed range and a hash of the
reviewed tree. ``scripts/security_gate.py`` requires a matching record before
a phase can advance (REQ-SECURITY-REVIEW-008). Records before that script
exists were made by hand and carry no tree hash.

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

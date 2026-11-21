Security
========

The STRIDE threat model and the risks the operator has accepted. Both are
written by the security review skill: at design time, after docs approval,
and after implementation, once arch-review has approved (FEAT-SECURITY-REVIEW).

Threats are ``threat`` needs (``THREAT-<CONTAINER>-NNN``), each tagged with
the C4 element it concerns and linked to the requirement that mitigates it.
Accepted risks are ``risk`` needs (``RISK-NNN``) with the operator's
rationale and the run in which they were accepted.

.. toctree::
   :maxdepth: 1
   :glob:

   threat-model/*
   accepted-risks

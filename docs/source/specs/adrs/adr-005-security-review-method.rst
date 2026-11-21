ADR-005: Security review is LLM-led STRIDE + OWASP on Opus, with the operator deciding every finding
====================================================================================================

.. adr:: Security review is LLM-led STRIDE + OWASP on Opus, with the operator deciding every finding
   :id: ADR-005
   :status: accepted
   :c4_scope: security_review sdd_orchestrator

   **Context**: FEAT-SECURITY-REVIEW adds a security agent at design time and
   after implementation. The method, the model and who decides on findings
   shape cost, coverage and trust.

   **Decision**: The security agent runs on Opus. At design time it builds a
   STRIDE threat model per new or changed C4 container and trust boundary.
   After implementation it checks the run's code against OWASP ASVS / Top 10
   concerns and verifies each threat's mitigation and test. Every finding
   goes to the operator, who chooses what happens. No severity triggers an
   automatic reset. No scanners or dependency audits are run.

   **Rationale**: STRIDE fits the C4 docs the pipeline already keeps. OWASP
   covers the code-level classes of flaw that matter for the kinds of
   services this plugin builds. Security misses are expensive, so the
   strongest model is worth its cost on two runs per feature. The operator
   owns risk and scope trade-offs.

   **Consequences**: Each feature costs two Opus reviews. Results depend on
   model judgement, not on deterministic tools. Known-CVE dependencies are
   not caught by this feature. Operator gates add two interaction points per
   run.

   **Alternatives considered**:

   - Running semgrep / bandit / npm audit / pip-audit when installed:
     not chosen for this feature; can be added later as a separate sensor.
   - Dependency review (licence, maintenance, CVEs): not chosen.
   - Automatic reset on critical/high findings: rejected; the operator
     decides every finding.
   - Sonnet by default with escalation: rejected in favour of Opus always.

---
name: arch-review
description: >
  SDD architecture review skill. Runs after all implement tasks are green.
  Reviews the new code against requirements, ADRs, and all three C4 model
  layers. Surfaces boundary violations, missing coverage, and ADR breaches.
  Presents findings to user with an approval gate. Signals reset if findings
  imply undocumented requirements. Called autonomously by the sdd skill.
---

# Arch-Review Skill

You run architecture review after all implement and test tasks have closed
with `s=ok`. Your job is to verify the implementation fits the architecture,
not just the individual requirements.

**You run inline in the main-agent context, not as a spawned sub-agent.** You
spawn a test-quality reviewer sub-agent (step 2b) and, on "fix", a coder
worker (step 8) via the Agent tool — only the main agent can do that.

Read `skills/rules/RULES.md` before starting.

---

## Inputs

- `FEAT_ID` — feature identifier
- `RUN_ID` — run identifier
- `EPIC_ID` — bd epic ID
- `CLAUDE_PROJECT_DIR` — project root

---

## Workflow

```
1. COLLECT       — gather all artifacts from this run
2. TEST QUALITY  — static sensor + LLM review on all test files
3. REQ CHECK     — verify every requirement is covered and accepted
4. BOUNDARY      — verify code lives in the declared C4 component
5. ADR CHECK     — verify no ADR is violated
6. C4 COHERENCE  — verify implementation matches L1/L2/L3 descriptions
7. SUMMARIZE     — present findings to user
8. GATE          — user approves or requests changes
```

---

## Step 1 — Collect Artifacts

```bash
bd list --label "run=$RUN_ID" --label "agent=coder"
```

For each coder issue, read the artifacts:

```bash
bd show <id>
```

Parse all `[artifact path=...]` entries. Collect the unique set of file paths.

Also collect all tester issues and their test file paths.

---

## Step 2 — Test Quality Check

Two sensors run in order. Both must pass before advancing to step 3.

### 2a. Static sensor (script)

Collect all test file paths from tester issue artifacts:

```bash
bd list --label "run=$RUN_ID" --label "agent=tester"
# for each: bd show <id>, parse [artifact path=...] entries
```

Run the static linter:

```bash
python skills/arch-review/scripts/lint_tests.py <test_file_1> <test_file_2> ...
```

The script exits with code 1 if any critical or major finding exists.
Capture the output — it maps directly to `[note]` entries in the summary.

Critical findings (no assertions, empty body, `assert True`) are **blocking**:
the tester issue must be reopened and the finding fixed before arch-review
can continue. Do not advance to step 3 with unresolved critical findings.

Major findings (generic names, sole `is not None` assertion) are **major**
findings in the summary. They go to the user approval gate, not an automatic
block — but the user must explicitly accept them.

### 2b. LLM sensor (reviewer sub-agent)

After the static sensor passes (or user accepts major findings), spawn a
reviewer sub-agent to read the test files for subtler problems:

```python
Agent(
    model="haiku",
    description="Test quality review",
    prompt=f"""
Read skills/rules/TESTING.md before starting.

Review these test files for quality problems that static analysis cannot catch:

{chr(10).join(test_file_paths)}

For each file, check:
1. Do tests assert on observable behaviour or on internal implementation details?
   (asserting on a private method call or internal field = implementation detail)
2. Are any tests duplicates of each other (same behaviour, different variable names)?
3. Do test names describe behaviour? (test_<what>_<condition>_<expected>)
4. Do tests have multiple independent Act phases? (split into separate tests)
5. Does the test suite cover all sub-cases of the acceptance criterion?
   The acceptance criterion for this run is: {acceptance_criteria}
6. Are there magic literals that obscure intent?

For each problem found, output:
  SEV: major|info
  FILE: <path>:<line>
  TEST: <test_name>
  ISSUE: <what is wrong and why it matters>

If no problems are found, output: QUALITY OK
"""
)
```

Parse the reviewer output. Major findings go into the summary.
Info findings go into the summary as info.

---

## Step 3 — Requirement Coverage Check

Read the feature's requirements:

```bash
grep -rn ".. req::" docs/specs/features/
grep -rn ":id: REQ" docs/specs/features/
```

For each `REQ-XXX-NNN` belonging to `FEAT_ID`:

**Coverage**: check that at least one artifact file carries this REQ in
its `[origin]` header (`req=REQ-XXX-NNN`).

```bash
grep -r "req=REQ-XXX-NNN" <artifact files>
```

If a requirement has zero coverage: **critical finding** — the requirement
was planned but not implemented.

**Acceptance**: read the `[accept]` field from the requirement RST. Find the
tester result for the task carrying this REQ:

```bash
bd list --label "run=$RUN_ID" --label "req=REQ-XXX-NNN" --label "agent=tester"
bd show <tester_id>
```

Read the `[suite]` block. If `f=` > 0 or any `[test s=fail]` entries exist
for acceptance-critical tests: **major finding**.

---

## Step 4 — C4 Boundary Check

For each artifact file, read its `[origin]` header:

```python
# [origin ref=... req=... c4=<container>/<component>]
```

Verify:
1. The declared `c4=<container>/<component>` matches what the requirement
   specified (`:c4_component:` and `:c4_container:` in the RST).
2. The file's filesystem path is consistent with the declared component.
   (A file in `src/auth/` claiming `c4=payments/processor` is a violation.)

**Boundary violation** (major finding): code declared to one component
but living in another component's directory or calling across component
boundaries it doesn't own.

---

## Step 5 — ADR Compliance Check

Read all ADRs:

```bash
ls docs/specs/adrs/
cat docs/specs/adrs/adr-*.rst
```

For each accepted ADR, check the implementation:

- **Testing framework ADR**: are the test files using the declared framework?
- **Architecture pattern ADRs**: do the new components use the mandated patterns?
- **Integration ADRs**: are integrations implemented via the specified mechanism?

Flag any deviation as a finding with the ADR ID.

---

## Step 6 — C4 Coherence Check

### L1 — System Context

Read `docs/architecture/context.rst`. Does the implementation introduce any
new external dependencies not shown in the context diagram? If so: finding
(context diagram needs updating — likely a new requirement).

### L2 — Containers

Read `docs/architecture/containers.rst`. Does the new code introduce calls
between containers not shown in the container diagram? If so: finding.

### L3 — Components

For each C4 component touched by this feature:

```bash
cat docs/architecture/components/<component>.rst
```

Compare the component description (responsibility, patterns, ownership)
to what was actually implemented:
- Does the implementation stay within the stated responsibility?
- Are the patterns from the description used?
- Is the ownership correct (no data owned by the wrong component)?

---

## Step 7 — Summarize Findings

Group findings by severity:

```
## Architecture Review — FEAT_ID (run=RUN_ID)

### Test Quality
tests/test_auth.py: OK (script sensor clean, LLM review: no issues)
tests/test_token.py: ⚠ MAJOR test_token — sole assertion is 'assert result is not None'
tests/test_user.py: ⚠ MAJOR test_1 — name too generic

### Coverage
REQ-XXX-001: covered — all tests passing
REQ-XXX-002: ⚠ not covered — no artifact carries this req in [origin]

### Boundary
src/auth/token.py: OK (c4=backend/auth_service matches requirement)
src/payments/processor.py: ⚠ VIOLATION — declared c4=backend/auth_service
  but lives in payments/ directory and calls PaymentRepo

### ADR Compliance
ADR-003 (JWT tokens): compliant
ADR-007 (Repository pattern): ⚠ auth_service calls DB directly, bypassing
  UserRepo interface

### C4 Coherence
L1 context: no new external systems introduced
L2 containers: no new cross-container calls
L3 components: auth_service description says "no direct DB access" —
  implementation violates this

### Summary
Critical: 0
Major:    2 (boundary violation, ADR-007 breach)
Minor:    0
Info:     1 (context diagram could be updated to show JWT issuer)
```

---

## Step 8 — User Approval Gate

Present the summary, then:

```
## Arch Review complete

<summary as above>

**Options**:
- **approve** — accept findings as-is, close the SDD run
- **fix [finding]** — I will address the listed findings and re-run the review
- **revise docs [what]** — finding implies a missing or wrong requirement;
  sdd will reset to the docs phase
```

**Do not close the epic until the user explicitly approves.**

### On "fix": re-run review

Create a new coder bd issue for the fix, spawn a worker, verify the fix,
re-run steps 2–5 for the affected findings. Re-present the summary.

### On "revise docs": signal reset

Write a reset signal to the epic:

```bash
bd epic update $EPIC_ID --label "phase=reset" \
  --body "arch-review: reset triggered. Finding: <description>"
```

Return to sdd, which bounces to docs phase and increments reset counter.

---

## Closing the Run

After user approval with no outstanding major/critical findings:

```bash
# Close the epic
bd epic close $EPIC_ID

# Update all feature requirements to status=implemented
# (update the RST files in docs/specs/features/)
```

Report to sdd:

```
[arch-review run=<RUN_ID> feat=<FEAT_ID> s=approved]
[req id=REQ-XXX-NNN s=implemented]
[/arch-review]
```

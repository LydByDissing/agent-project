# Test Quality Guide — Shared Reference

Read this before writing any test. The test suite is the proof that the
implementation satisfies the acceptance criteria. A test that always passes
is worse than no test: it creates false confidence.

The arch-review skill runs a static sensor (`lint_tests.py`) and an LLM
review on every test file written in a run. Poor quality is a blocking finding.

---

## Core Philosophy

**Test behaviour, not implementation.**

A test must fail when the system stops behaving correctly. A test that only
verifies internal structure (method was called, field is set) will pass when
the system is broken and fail when you refactor perfectly working code.

The acceptance criterion in the bd task (`[accept]`) is the contract. The
test suite is the proof. If the acceptance criterion says "valid credentials
return a JWT within 500ms", the test must assert that: call with valid
credentials, measure time, assert JWT is present and structurally valid.

---

## Naming

```
test_<what>_<condition>_<expected_outcome>
```

- `what`: the behaviour or capability being tested (not the function name)
- `condition`: the input state or scenario
- `expected_outcome`: what the system does

Good:
```python
def test_login_with_valid_credentials_returns_jwt(): ...
def test_login_with_wrong_password_returns_401(): ...
def test_token_expires_after_24_hours(): ...
def test_create_user_with_duplicate_email_raises_conflict(): ...
```

Bad:
```python
def test_login(): ...          # no condition or outcome
def test_auth_service(): ...   # tests a class, not a behaviour
def test_1(): ...              # meaningless
def test_it_works(): ...       # what works? under what condition?
```

---

## Structure (AAA)

Every test has three sections, always in this order:

```python
def test_login_with_valid_credentials_returns_jwt():
    # Arrange — set up the world
    user = make_user(email="a@b.com", password="correct")
    
    # Act — trigger the behaviour
    result = auth_service.login("a@b.com", "correct")
    
    # Assert — verify the outcome
    assert result.token is not None
    assert result.expires_in == 86400
```

One behaviour per test. One Act block per test. If you find yourself writing
two separate Act blocks, split it into two tests.

Blank-line separation between sections is recommended but not mandatory.
Never mix Arrange and Assert code.

---

## Unit Tests

Unit tests verify a single component in isolation from its dependencies.

### Rules

**Test one behaviour at a time.** One test = one `[accept]` criterion or one
sub-case of it. Never group unrelated assertions.

**Descriptive failure messages.** When an assertion fails, the output must
make the problem obvious without reading the test code:

```python
# bad
assert result == expected

# good
assert result == expected, f"login returned {result!r}, expected token with exp={expected.expires_in}"
```

**Don't test private implementation.** If the test imports or patches an
internal function (`_hash_password`, `_encode_claims`), it is testing
implementation. Test the public surface only.

**Don't assert `is not None` as the sole check.** It proves existence, not
correctness. Assert what the value actually is or contains.

```python
# bad
assert result is not None

# good
assert result.status_code == 200
assert "token" in result.json()
```

**Stub external I/O, not your own code.** Acceptable mocks: third-party HTTP
calls, time (`datetime.now`), random, external queues. Not acceptable: mocking
methods on the class under test, mocking your own repository interfaces.

**Test must be independent.** No shared mutable state between tests. Each test
sets up its own world. Tests can run in any order.

---

## Integration Tests

Integration tests verify that components work correctly with their real
dependencies.

### Rules

**Never mock the database.** Use a real database, seeded with fixtures and
cleaned up after each test (transaction rollback or fixture teardown).
Mocked DB tests have historically passed while production migrations broke.

**Test the boundary.** Call the integration test at the same level a real
client would: the HTTP handler, the queue consumer, the CLI entry point.
Not the internal service method.

**Idempotent.** Running the test suite twice in a row must produce the same
result. Tests that leave state behind contaminate other tests.

**Fixture cleanup is mandatory.** Use `pytest` fixtures with `yield` to
guarantee cleanup even on failure:

```python
@pytest.fixture
def db_user(db_session):
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.commit()
    yield user
    db_session.delete(user)
    db_session.commit()
```

**Test realistic inputs.** Use values that resemble production data, not
trivially simple ones. `email="a@b.com"` is acceptable; `name="x"` for a
name field that has a 2-character minimum is a test that will never catch
boundary bugs.

---

## Anti-Patterns (automatic findings by lint_tests.py)

These are detected statically and produce blocking findings in arch-review.

| Anti-pattern | Severity | Why |
|---|---|---|
| No assertions in test | critical | Test proves nothing; always passes |
| Empty test body (`pass` / `...`) | critical | Not a test |
| `assert True` or `assert 1` | critical | Always passes; hides bugs |
| `assert result is not None` as only assertion | major | Proves existence, not behaviour |
| Generic name (`test_1`, `test_it`, `test_func`) | major | Impossible to diagnose on failure |
| Test body > 60 lines | info | Likely testing multiple behaviours |

These are detected by LLM review and produce findings (not always blocking):

| Anti-pattern | Why |
|---|---|
| Assertions on private/internal state | Breaks on refactor; doesn't prove behaviour |
| Mock of the unit under test's own methods | You're testing the mock, not the code |
| Test name describes code structure, not behaviour | Fails to communicate intent |
| Multiple independent Act sections | Split into separate tests |
| Magic literals with no explanation | Use named variables or constants |

---

## Acceptance Criterion → Test Mapping

Every `[accept]` in the bd task must map to at least one test. Before writing
the result DSL, do this check explicitly:

```
[accept] → test covering it
valid credentials → JWT within 500ms   → test_login_valid_credentials_returns_jwt_under_500ms
invalid credentials → 401              → test_login_invalid_password_returns_401
                                        test_login_unknown_email_returns_401
```

If an acceptance criterion has no test: the task is not done.

---

## See Also

- `skills/arch-review/scripts/lint_tests.py` — static sensor
- `skills/rules/RULES.md` — code style and model selection

---

## Mutation checking — the only evidence an assertion is live

A green suite cannot distinguish *"the boundary held"* from *"the boundary was never reached"*.
Inspection cannot either: a test that names a boundary looks identical to one that exercises it.
**Break the production code on purpose and count which tests fail.**

```
1. apply one mutation that violates the rule the test claims to enforce
2. run the suite; record WHICH tests failed and HOW MANY
3. revert, and verify the tree is byte-identical to the green one
4. report the counts
```

**A mutation that breaks only ONE test is a warning, not a pass.** In one run of this pipeline it
meant the test was passing for the wrong reason four separate times:

- `preflight` moved after a write broke 1 test — because the stub refused every *read* too, so the
  mutated run stopped before the write anyway. **The fence was passing, not the ordering.**
- A reconcile guard removed broke 1 test — because the caller reconciled first, so the divergence
  never reached the code under test. The case that mattered had **no test at all**.
- A sleeve-ordering mutation broke 1 test — because that test's expected state *happened to equal*
  the enum order, so it could not tell "follows the report" from "iterates the enum".
- By contrast, swapping two ordered operations broke **23 tests in 3 classes**. That is what a live
  assertion looks like beside a decorative one.

**Restoring is part of the technique and it fails silently.** A copy that preserves mtime lets the
build reuse the *mutated* class file, so the next run tests the mutation and reports it as a real
failure. Touch the file, or clean. Equally: a renamed resource leaves the old copy in the build
output, and the classpath — not the source tree — is what runs.

## A positive control must exercise the thing under test

A control built from the same constant as the check tests **the constant, not the check**:

```java
// WORTHLESS: never calls the scan it guards
String sample = "package x;\n" + FORBIDDEN_IMPORT + "Y;";
assertTrue(sample.contains(FORBIDDEN_IMPORT));

// REAL: plants files on disk and runs the actual scan
Files.writeString(tmp.resolve("Bad.java"), "package x;\n" + FORBIDDEN_IMPORT + "Y;");
assertEquals(List.of(planted.toString()), offendersAmong(javaFilesUnder(tmp)));
```

The first form was written *by the author who had spent that same session reporting this exact
defect in other people's code*. Knowing the rule does not protect you, because a broken control
looks exactly like a control.

**A rule asserting an absence proves nothing until it has been shown to bite on a presence.** If a
test says "no write route exists" or "no secret appears in the output", it needs a planted write
route and a planted secret.

## Boundaries: adjacent, and different on each side

- Put the value **adjacent** to the threshold (±1 in the smallest unit the type carries). A 10-day
  limit tested with 20 and 60 would have passed for any limit from 1 to 19.
- Assert the two sides are **different**, not both equal to the same number. A commission floor
  asserted at 22.00 on *both* sides of its crossover is also exactly what a floor-only
  implementation returns — the percentage leg was untested by a test that appeared to test it.
- Where a statute or spec says "exceeds", the boundary is one unit wide. Assert the exact value is
  *below*, and mutate `>` to `>=` to prove the test notices.

## Secrets: grep the rendered output, never the code

Reading the code and concluding it looks fine misses the leaks the *language* generates for you.
Collect every rendered string a component can emit — messages, `toString()`, exception messages
**and stack traces**, every captured log event — assert the collection's size so a sweep that
silently stops covering something fails, then grep all of it for planted sentinels. Found this way,
never by reading:

- a `record` whose component was a bearer token printed it from its **compiler-generated**
  `toString()`;
- an "unreadable file" message embedded a parse error, and the parser quotes the offending
  **source** — which was the credential file.

For container images, scan **per layer**: a file copied and then deleted in a later layer is still
in the image, and a merged-filesystem check finds nothing there.

# [origin ref=llm-dsl-2zv1.8 req=REQ-SECURITY-REVIEW-010 c4=sdd_skills/security_review]
#   [intent]Adversarial audit of redact-check: segmented, wrapped and embedded secrets must be detected, sha allowlist must stay narrow, real docs must pass, output must stay masked.[/intent]
# [/origin]

import base64
import json
import os
import random
import string
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = Path(os.environ.get("SECGATE_UNDER_TEST", str(ROOT / "scripts" / "security_gate.py")))
ALNUM = string.ascii_letters + string.digits
B64URL = ALNUM + "-_"


def rnd(seed: int, n: int, alpha: str = ALNUM) -> str:
    r = random.Random(seed)
    while True:
        v = "".join(r.choice(alpha) for _ in range(n))
        if any(c.isdigit() for c in v) and any(c.isalpha() for c in v):
            return v


def rhex(seed: int, n: int) -> str:
    r = random.Random(seed)
    return "".join(r.choice("0123456789abcdef") for _ in range(n))


def run(*args: str, cwd: Path = ROOT):
    r = subprocess.run([sys.executable, str(GATE), "redact-check", *args], capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def scan(tmp_path: Path, text: str, name: str = "a.rst"):
    f = tmp_path / name
    f.write_text(text)
    rc, so, se = run("--paths", str(f))
    return rc, so + se


def masked(secret: str, out: str) -> bool:
    return secret not in out and all(secret[i : i + 6] not in out for i in range(5, len(secret) - 5))


def detect(tmp_path: Path, secret: str, text: str, name: str = "a.rst"):
    rc, out = scan(tmp_path, text, name)
    assert rc == 1, "leak not detected"
    assert "a.rst:" in out or name in out
    assert masked(secret, out), out


@pytest.mark.xfail(strict=True, reason="major: 60% segment rule skips word-prefixed hyphen secrets")
def test_hyphen_segmented_prod_db_prefix(tmp_path):
    s = "prod-db-" + rnd(1, 24)
    detect(tmp_path, s, f"password {s}\n")


@pytest.mark.xfail(strict=True, reason="major: 60% segment rule skips word-prefixed hyphen secrets")
def test_hyphen_segmented_long_variants(tmp_path):
    for i, pre in enumerate(("prod-db-", "stage-api-key-", "my-live-")):
        s = pre + rnd(20 + i, 28)
        rc, out = scan(tmp_path, f"x {s}\n", f"v{i}.rst")
        assert rc == 1, pre


def test_underscore_token_prefix(tmp_path):
    s = "token_" + rnd(2, 30)
    detect(tmp_path, s, f"{s}\n")


def test_underscore_segmented_prod_db(tmp_path):
    s = "prod_db_" + rnd(3, 24)
    detect(tmp_path, s, f"pw={s}\n")


@pytest.mark.xfail(strict=True, reason="major: 60% segment rule skips word-prefixed hyphen secrets")
def test_secret_with_alpha_digit_segments_hidden_by_sixty_percent_rule(tmp_path):
    s = "a-b-c-" + rnd(4, 26)
    rc, out = scan(tmp_path, f"{s}\n")
    assert rc == 1


def test_jwt_detected_and_masked(tmp_path):
    def b(o: bytes) -> str:
        return base64.urlsafe_b64encode(o).decode().rstrip("=")

    head = b(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    pay = b(json.dumps({"sub": rnd(5, 16), "iat": 1700000000}).encode())
    sig = rnd(6, 43, B64URL)
    jwt = f"{head}.{pay}.{sig}"
    detect(tmp_path, sig, f"Authorization: Bearer {jwt}\n")


def test_jwt_random_parts(tmp_path):
    parts = [rnd(30 + i, n, B64URL) for i, n in enumerate((36, 60, 43))]
    detect(tmp_path, parts[2], f"{'.'.join(parts)}\n")


def test_base64_blob_with_plus_and_slash(tmp_path):
    a, b, c, d = (rnd(40 + i, 40) for i in range(4))
    blob = a + "+" + b + "/" + c + "/" + d
    rc, out = scan(tmp_path, f"data {blob}\n")
    assert rc == 1
    assert masked(a, out) and masked(c, out)


def test_random_base64_blobs_always_detected(tmp_path):
    miss = []
    for seed in range(60):
        r = random.Random(seed)
        blob = base64.b64encode(bytes(r.randrange(256) for _ in range(66))).decode()
        rc, _ = scan(tmp_path, f"k {blob}\n", f"b{seed}.rst")
        if rc == 0:
            miss.append(seed)
    assert not miss, f"{len(miss)}/60 random 88-char base64 blobs undetected"


@pytest.mark.xfail(strict=True, reason="minor: line-based scan misses secrets wrapped over lines")
def test_prefix_key_split_across_lines(tmp_path):
    k = "AK" + "IA" + rnd(50, 16).upper()
    text = f"leaked key {k[:10]}\n{k[10:]}\n"
    rc, out = scan(tmp_path, text)
    assert rc == 1


@pytest.mark.xfail(strict=True, reason="minor: line-based scan misses secrets wrapped over lines")
def test_github_token_split_across_lines(tmp_path):
    k = "gh" + "p_" + rnd(51, 36)
    rc, out = scan(tmp_path, f"token {k[:18]}\n{k[18:]}\n")
    assert rc == 1


def test_key_in_backticks_and_literal(tmp_path):
    k = "AK" + "IA" + rnd(52, 16).upper()
    detect(tmp_path, k, f"see ``{k}`` and `{k}`\n")


def test_token_in_backticks(tmp_path):
    s = rnd(53, 40)
    detect(tmp_path, s, f"use `{s}` here\n")


def test_secret_in_rst_field(tmp_path):
    k = "gh" + "p_" + rnd(54, 36)
    detect(tmp_path, k, f".. threat:: T\n   :mitigation: rotate {k} now\n   :status: open\n")


def test_entropy_token_in_rst_field(tmp_path):
    s = rnd(55, 40)
    detect(tmp_path, s, f"   :mitigation: {s}\n")


def test_secret_in_markdown_link(tmp_path):
    k = "sk" + "-ant-" + rnd(56, 30, B64URL)
    detect(tmp_path, k, f"[docs](https://example.com/x?key={k})\n", "a.md")


def test_token_as_query_value_in_link(tmp_path):
    s = rnd(57, 40)
    detect(tmp_path, s, f"[docs](https://example.com/x?a=1&token={s}&b=2)\n", "a.md")


@pytest.mark.xfail(strict=True, reason="minor: directory expansion skips svg text under security docs")
def test_secret_in_svg_under_security_dir_via_directory(tmp_path):
    d = tmp_path / "docs" / "source" / "security"
    d.mkdir(parents=True)
    k = "AK" + "IA" + rnd(58, 16).upper()
    (d / "fig.svg").write_text(f'<svg><text x="1">{k}</text></svg>\n')
    rc, so, se = run("--paths", str(d))
    assert rc == 1, "svg skipped in directory expansion"
    assert masked(k, so + se)


def test_secret_in_svg_explicit_path_scanned(tmp_path):
    k = "AK" + "IA" + rnd(59, 16).upper()
    f = tmp_path / "fig.svg"
    f.write_text(f"<svg><text>{k}</text></svg>\n")
    rc, so, se = run("--paths", str(f))
    assert rc == 1 and masked(k, so + se)


@pytest.mark.xfail(strict=True, reason="minor: reviews.rst allowlist covers every cell")
def test_hex64_in_reviews_outcome_cell(tmp_path):
    h = rhex(60, 64)
    rc, out = scan(tmp_path, f"   * - 87708f1a\n     - post\n     - passed key {h}\n", "reviews.rst")
    assert rc == 1, "reviews.rst allowlists any 40/64 hex in any cell"


@pytest.mark.xfail(strict=True, reason="minor: allowlist keyed on file name reviews.rst anywhere")
def test_hex_in_reviews_named_file_elsewhere(tmp_path):
    d = tmp_path / "other"
    d.mkdir()
    h = rhex(61, 64)
    rc, out = scan(d, f"value {h}\n", "reviews.rst")
    assert rc == 1, "any file named reviews.rst gets the allowlist"


def test_hex_32_in_reviews_still_fails(tmp_path):
    h = rhex(62, 32)
    rc, out = scan(tmp_path, f"     - {h}\n", "reviews.rst")
    assert rc == 1 and masked(h, out)


def test_hex_128_in_reviews_still_fails(tmp_path):
    h = rhex(63, 128)
    rc, out = scan(tmp_path, f"     - {h}\n", "reviews.rst")
    assert rc == 1


@pytest.mark.parametrize("n", (40, 64))
def test_lowercase_hex_non_sha_context_fails(tmp_path, n):
    h = rhex(70 + n, n)
    rc, out = scan(tmp_path, f"the secret is {h}\n")
    assert rc == 1 and masked(h, out)


def test_hex_in_non_sha_context_in_other_rst_fails(tmp_path):
    h = rhex(71, 64)
    rc, out = scan(tmp_path, f"   * - {h}\n", "notes.rst")
    assert rc == 1


def test_sha_on_base_line_passes(tmp_path):
    h = rhex(72, 40)
    assert scan(tmp_path, f"Base: {h}\n")[0] == 0
    assert scan(tmp_path, f"base: {h}\n")[0] == 0
    assert scan(tmp_path, f"Range: {h}..{rhex(73, 40)}\n")[0] == 0


@pytest.mark.xfail(strict=True, reason="minor: sha context allowlists whole line")
def test_sha_context_does_not_hide_other_hex_on_line(tmp_path):
    h = rhex(74, 64)
    rc, out = scan(tmp_path, f"base: {rhex(75, 40)} password {h}\n")
    assert rc == 1


def test_sha_context_does_not_hide_mixed_token(tmp_path):
    s = rnd(76, 40)
    rc, out = scan(tmp_path, f"base={rhex(77, 40)} {s}\n")
    assert rc == 1 and masked(s, out)


@pytest.mark.xfail(strict=True, reason="minor: uppercase hex below entropy threshold, not matched by HEX rule")
def test_uppercase_hex_secret_detected(tmp_path):
    h = rhex(78, 64).upper()
    rc, out = scan(tmp_path, f"key {h}\n")
    assert rc == 1


def test_control_repo_docs_and_learn_pass():
    for p in ("docs/source", "learn"):
        if (ROOT / p).exists():
            rc, so, se = run("--paths", str(ROOT / p))
            assert rc == 0, so + se


@pytest.mark.skipif("SECGATE_UNDER_TEST" in os.environ, reason="default paths resolve against the script location")
def test_control_repo_default_scan_passes():
    rc, so, se = run()
    assert rc == 0, so + se


def test_control_prose_like_content_passes(tmp_path):
    u = [str(uuid.uuid5(uuid.NAMESPACE_DNS, f"x{i}")) for i in range(5)]
    txt = (
        f"Run ids {' '.join(u)} appear in prose.\n"
        "path /home/user/projects/some-long-directory-name/another-long-directory/file_name_with_parts.py\n"
        "https://example.com/search?q=long+query+string&utm_source=newsletter&utm_medium=email&page=3&sort=desc\n"
        "def compute_security_gate_redaction_result_for_run(feature_identifier, run_identifier):\n"
        "class SecurityGateRedactionAuditFixtureBuilderForTests:\n"
        "MAX_REDACT_ENTROPY_THRESHOLD_FOR_TOKENS_IN_DOCS = 4\n"
        ".. threat:: THREAT-SDD-SKILLS-007\n   :links: REQ-SECURITY-REVIEW-010, ADR-005\n"
        "FEAT-SECURITY-REVIEW-87708f1a-reset3 and llm-dsl-2zv1.8 and THREAT-SDD-SKILLS-007\n"
    )
    rc, out = scan(tmp_path, txt)
    assert rc == 0, out


def test_output_masking_across_all_kinds(tmp_path):
    secrets = {
        "aws": "AK" + "IA" + rnd(80, 16).upper(),
        "gh": "gh" + "p_" + rnd(81, 36),
        "ent": rnd(82, 40),
        "hex": rhex(83, 64),
        "seg": "prod-db-" + rnd(84, 24),
    }
    text = "\n".join(f"{k} {v}" for k, v in secrets.items()) + "\n"
    f = tmp_path / "m.rst"
    f.write_text(text)
    rc, so, se = run("--paths", str(f))
    out = so + se
    assert rc == 1
    for k, v in secrets.items():
        assert masked(v, out), k
    assert "m.rst:1:" in out and "m.rst:2:" in out and "m.rst:3:" in out and "m.rst:4:" in out


def test_text_file_output_masked(tmp_path):
    k = "gh" + "p_" + rnd(85, 36)
    f = tmp_path / "msg.txt"
    f.write_text(f"subject\n\nleak {k}\n")
    rc, so, se = run("--text-file", str(f), "--paths", str(tmp_path / "none.rst"))
    assert rc == 1 and masked(k, so + se)

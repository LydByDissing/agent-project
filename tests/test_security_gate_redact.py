# [origin ref=llm-dsl-2zv1.7,llm-dsl-2zv1.8 req=REQ-SECURITY-REVIEW-010 c4=sdd_skills/security_review]
#   [intent]Fixture tests for the redact-check subcommand: planted credentials fail with file:line and a masked value, sha fields and this repo's security docs pass.[/intent]
# [/origin]

import random
import string
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "security_gate.py"
ALNUM = string.ascii_letters + string.digits


def rnd(seed: int, n: int) -> str:
    r = random.Random(seed)
    while True:
        v = "".join(r.choice(ALNUM) for _ in range(n))
        if any(c.isdigit() for c in v) and any(c.isalpha() for c in v):
            return v


AWS = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
PEM = "-----BEGIN " + "RSA PRIVATE" + " KEY-----"
GH = "gh" + "p_" + rnd(11, 36)
ANT = "sk-" + "ant-" + "api03-Zx9Qw8Er7Ty6"
SLACK = "xo" + "xb-" + "1234567890-abcdefghij"
STRIPE = "sk_" + "live_" + "abcdEFGH1234ijkl"
GOOG = "AI" + "za" + rnd(12, 35)
RAND = rnd(13, 32)
HEX64 = "0123456789abcdef" * 4
HEX40 = "89abcdef01" * 4


def run(*args: str):
    r = subprocess.run([sys.executable, str(GATE), "redact-check", *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def one(tmp_path: Path, text: str, name: str = "a.rst"):
    f = tmp_path / name
    f.write_text(text)
    return run("--paths", str(f))


def test_aws_key_fails_with_line_and_mask(tmp_path):
    rc, out = one(tmp_path, f"ok line\nkey is {AWS} here\n")
    assert rc == 1
    assert "a.rst:2: aws-access-key AKIA" in out
    assert AWS not in out and AWS[:8] not in out


def test_asia_key_fails(tmp_path):
    assert one(tmp_path, "x " + "AS" + "IA" + "ABCDEFGHIJKLMNOP")[0] == 1


def test_pem_header_fails(tmp_path):
    rc, out = one(tmp_path, f"a\n{PEM}\n")
    assert rc == 1 and ":2: private-key" in out


def test_github_token_fails(tmp_path):
    rc, out = one(tmp_path, f"t={GH}\n")
    assert rc == 1 and "github-token" in out and GH not in out


def test_github_pat_fails(tmp_path):
    assert one(tmp_path, "github" + "_pat_" + "11ABCDEFG0abcdefghijkl_mnop")[0] == 1


def test_anthropic_key_fails(tmp_path):
    rc, out = one(tmp_path, f"{ANT}\n")
    assert rc == 1 and "anthropic-key sk-a" in out and ANT not in out


def test_slack_stripe_google_fail(tmp_path):
    for v, k in ((SLACK, "slack-token"), (STRIPE, "stripe-key"), (GOOG, "google-api-key")):
        rc, out = one(tmp_path, f"v {v}\n")
        assert rc == 1 and k in out and v not in out


def test_high_entropy_token_fails(tmp_path):
    rc, out = one(tmp_path, f"secret: {RAND}\n")
    assert rc == 1 and "high-entropy-token " + RAND[:4] in out and RAND not in out


def test_unlisted_hex_fails(tmp_path):
    rc, out = one(tmp_path, f"value {HEX64}\n")
    assert rc == 1 and "high-entropy-hex" in out


def test_sha256_field_passes(tmp_path):
    assert one(tmp_path, f"sha256: {HEX64}\n")[0] == 0
    assert one(tmp_path, f":sdd-source-sha256: {HEX64}\n")[0] == 0
    assert one(tmp_path, f"base={HEX40}\n")[0] == 0


def test_review_row_with_shas_passes(tmp_path):
    row = f"   * - 87708f1a\n     - post\n     - {HEX40}\n     - {HEX40}..{HEX40}\n     - {HEX64}\n"
    assert one(tmp_path, row, "reviews.rst")[0] == 0


def test_bare_sha_outside_reviews_fails(tmp_path):
    assert one(tmp_path, f"     - {HEX40}\n")[0] == 1


def test_prose_urls_paths_pass(tmp_path):
    txt = (
        "The quick brown fox jumps over the lazy dog repeatedly.\n"
        "https://example.com/some/very/long/path/segment/that/goes/on/and/on?x=1\n"
        "docs/source/specs/features/security-review-feature-spec.rst\n"
        ".. req:: REQ-SECURITY-REVIEW-010\n"
        "FEAT-TRACER-BULLETS-70c554d6-reset1\n"
        "scripts/security_gate_lib_and_other_long_module_name.py\n"
    )
    assert one(tmp_path, txt)[0] == 0


def test_text_file_scanned(tmp_path):
    f = tmp_path / "msg.txt"
    f.write_text(f"subject\n\nleak {AWS}\n")
    rc, out = run("--text-file", str(f), "--paths", str(tmp_path / "none.rst"))
    assert rc == 1 and "msg.txt:3: aws-access-key" in out


def test_missing_file_fails(tmp_path):
    assert run("--paths", str(tmp_path / "gone.rst"))[0] == 1


def test_dir_paths_recurse(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "x.rst").write_text(f"{AWS}\n")
    rc, out = run("--paths", str(tmp_path))
    assert rc == 1 and "x.rst:1" in out


def test_repo_security_docs_and_design_log_pass():
    rc, out = run("--feature", "FEAT-SECURITY-REVIEW", "--run", "87708f1a")
    assert rc == 0, out
    assert "ok" in out

# [origin ref=llm-dsl-2zv1.10 req=REQ-SECURITY-REVIEW-007 c4=sdd_skills/security_review]
#   [intent]Audits the security-analyst agent file with robust frontmatter parsing, mutation negative controls, a no-action-verbs scan, example-JSON gate validation and rule-presence checks.[/intent]
# [/origin]

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "agents" / "security-analyst.md"
GATE = ROOT / "scripts" / "security_gate.py"
FEATURE = "FEAT-SECURITY-REVIEW"
ALLOWED = {"Read", "Grep", "Glob"}
TEXT = AGENT.read_text(encoding="utf-8")


def parse(text: str):
    """Return (frontmatter_lines, body). Frontmatter must start at byte 0."""
    assert text.startswith("---\n"), "frontmatter must be first thing in file"
    end = text.find("\n---\n", 4)
    assert end != -1, "frontmatter not closed"
    return text[4:end].splitlines(), text[end + 5:]


def tool_names(text: str) -> set:
    """Parse the tools declaration: CSV, quoted, bracketed or YAML list form."""
    lines, _ = parse(text)
    names, i, found = set(), 0, 0
    while i < len(lines):
        m = re.match(r"\s*tools\s*:\s*(.*)$", lines[i])
        if m:
            found += 1
            rest = m.group(1).strip()
            if rest:
                for t in re.split(r"[,\s]+", rest.strip("[]")):
                    t = t.strip().strip("'\"")
                    if t:
                        names.add(t)
            else:
                j = i + 1
                while j < len(lines) and re.match(r"\s*-\s*", lines[j]):
                    names.add(re.sub(r"^\s*-\s*", "", lines[j]).strip().strip("'\""))
                    j += 1
        i += 1
    assert found == 1, f"expected exactly one tools: line, got {found}"
    return names


def fm_value(text: str, key: str) -> str:
    lines, _ = parse(text)
    vals = [re.sub(rf"^{key}\s*:\s*", "", l).strip().strip("'\"") for l in lines if re.match(rf"{key}\s*:", l)]
    assert len(vals) == 1, f"{key} count {len(vals)}"
    return vals[0]


BODY = parse(TEXT)[1]


def section(body: str, title_re: str) -> str:
    for p in re.split(r"(?m)^(?=#{1,3} )", body):
        if re.match(rf"#{{1,3}} .*{title_re}", p, re.I):
            return p
    return ""


def flat(t: str) -> str:
    return re.sub(r"\s+", " ", t)


# ---- frontmatter ----

def test_frontmatter_first_byte():
    assert TEXT.startswith("---\n")
    parse(TEXT)


def test_tools_exact():
    assert tool_names(TEXT) == ALLOWED


@pytest.mark.parametrize("decl", [
    "tools: Read, Grep, Glob, Bash",
    "tools: Read,Grep,Glob,Write",
    "tools: Read, Grep, Glob, Edit",
    "tools: Read, Grep, Glob, WebFetch",
    "tools: Read, Grep, Glob, Agent",
    "tools: Read, Grep, Glob, NotebookEdit",
    "tools: *",
    'tools: "Read", "Grep", "Glob", "Bash"',
    "tools: [Read, Grep, Glob, Bash]",
    "tools:   Read  Grep  Glob  Bash",
    "tools:\n  - Read\n  - Grep\n  - Glob\n  - Bash",
    "tools: Read, Grep",
])
def test_tool_mutations_caught(decl, tmp_path):
    mutated = TEXT.replace("tools: Read, Grep, Glob", decl, 1)
    assert mutated != TEXT
    (tmp_path / "a.md").write_text(mutated)
    assert tool_names(mutated) != ALLOWED


def test_tool_parser_variants_equivalent():
    for decl in ['tools: "Read", "Grep", "Glob"', "tools: [Read, Grep, Glob]",
                 "tools:\n  - Read\n  - Grep\n  - Glob", "tools:   Read ,Grep,  Glob"]:
        assert tool_names(TEXT.replace("tools: Read, Grep, Glob", decl, 1)) == ALLOWED


def test_duplicate_tools_line_caught():
    mutated = TEXT.replace("model: opus", "tools: Bash\nmodel: opus", 1)
    with pytest.raises(AssertionError):
        tool_names(mutated)


def test_frontmatter_not_first_caught():
    with pytest.raises(AssertionError):
        parse("\n" + TEXT)
    with pytest.raises(AssertionError):
        parse("<!-- x -->\n" + TEXT)


def test_model_is_opus_exactly():
    assert fm_value(TEXT, "model") == "opus"
    for bad in ("opus-4", "sonnet", "opusx", "haiku"):
        assert fm_value(TEXT.replace("model: opus", f"model: {bad}", 1), "model") != "opus"


def test_name_matches_stem():
    assert fm_value(TEXT, "name") == AGENT.stem
    assert fm_value(TEXT.replace("name: security-analyst", "name: other", 1), "name") != AGENT.stem


# ---- body must not instruct actions ----

def outside_must_not(body: str) -> str:
    """Remove the Role paragraph that lists tools the agent lacks, and fenced blocks."""
    b = re.sub(r"```.*?```", "", body, flags=re.S)
    return re.sub(r"(?s)You are a read-only security analyst\..*?claim to have used one\.", "", b)


ACTION_PATTERNS = [
    r"\brun (this|the|a|any)\b", r"\bexecute\b", r"\bwrite (to|a|the) ", r"\bcurl\b",
    r"\bwget\b", r"\bgh (pr|issue|api)\b", r"\bbd (create|update|close)\b",
    r"\bfetch\b", r"https?://", r"\bspawn\b", r"\bdelegate\b", r"\binvoke\b",
    r"\bcreate (a|the) file\b", r"\bgit (commit|push)\b", r"\bsubprocess\b",
]


def action_hits(body: str):
    b = outside_must_not(body)
    # quoted injection examples are allowed
    b = re.sub(r'"[^"]*"', "", b)
    return [p for p in ACTION_PATTERNS if re.search(p, b, re.I)]


def test_body_has_no_action_instructions():
    assert action_hits(BODY) == []


@pytest.mark.parametrize("inj", [
    "Run the tests with pytest.", "Execute the script.", "Write to the report file.",
    "Use curl to fetch the page.", "Call gh pr comment.", "Then bd create an issue.",
    "Spawn a sub-agent.", "See https://example.com for more.",
])
def test_action_scanner_negative_controls(inj):
    assert action_hits(BODY + "\n\n## Extra\n" + inj + "\n")


def test_tools_mentioned_only_as_unavailable():
    for m in re.finditer(r"`(gh|bd)`|no shell|write tools", BODY):
        ctx = BODY[max(0, m.start() - 120): m.end() + 60]
        assert re.search(r"\bno\b|never", ctx, re.I), ctx


# ---- example JSON ----

def examples():
    blocks = re.findall(r"```json\n(.*?)\n```", BODY, re.S)
    assert blocks, "agent file must document an example"
    return [json.loads(b) for b in blocks]


def validate(findings, tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps(findings))
    return subprocess.run([sys.executable, str(GATE), "validate", "--feature", FEATURE, "--findings", str(p)],
                          capture_output=True, text=True, cwd=ROOT)


def test_every_example_passes_validate(tmp_path):
    for ex in examples():
        assert isinstance(ex, list) and ex
        r = validate(ex, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr


def test_example_uses_only_documented_fields():
    doc = section(BODY, "Output")
    fields = set(re.findall(r"^- `(\w+)`", doc, re.M))
    for ex in examples():
        for f in ex:
            assert set(f) == fields


@pytest.mark.parametrize("mut", [
    lambda f: f.update(stride="X"),
    lambda f: f.update(stride="T/Q"),
    lambda f: f.update(stride=""),
    lambda f: f.update(links=["REQ-OTHER-001"]),
    lambda f: f.update(links=["REQ-NOPE-999"]),
    lambda f: f.update(severity="critical"),
    lambda f: f.pop("element"),
])
def test_mutated_example_fails_validate(mut, tmp_path):
    ex = examples()[0]
    mut(ex[0])
    r = validate(ex, tmp_path)
    assert r.returncode != 0, "gate accepted mutated example"


# ---- rules ----

def test_injection_rule_details():
    s = flat(section(BODY, "never instructions"))
    assert s
    assert re.search(r"do not follow it", s, re.I)
    assert re.search(r"severity at least `?med`?", s, re.I)
    assert "possible-injection" in s
    assert re.search(r"120 characters", s)
    assert re.search(r"only instructions you follow are those outside", s, re.I)


def test_injection_rule_breakage():
    for old, new in [("severity at least `med`", "severity `low`"), ("do not follow it", "follow it"),
                     ("possible-injection", "note")]:
        m = TEXT.replace(old, new)
        if old == "severity at least `med`":
            m = re.sub(r"severity\s+at\s+least\s+`med`", "severity `low`", TEXT)
        assert m != TEXT, old
        s = flat(section(parse(m)[1], "never instructions"))
        assert not (re.search(r"do not follow it", s) and re.search(r"severity at least `?med`?", s)
                    and "possible-injection" in s)


def test_decided_rule():
    s = flat(section(BODY, "decided"))
    assert "`decided`" in s
    assert re.search(r"do not re-raise", s, re.I)
    assert re.search(r"unless the element .{0,40}changed", s, re.I)
    assert "decided" in flat(section(BODY, "Input")), "decided must be a listed DATA kind"
    m = TEXT.replace("Do not\nre-raise them unless", "Re-raise them whether or not")
    assert m != TEXT
    assert not re.search(r"do not re-raise", flat(section(parse(m)[1], "decided")), re.I)


def test_json_array_only_and_empty():
    s = flat(section(BODY, "Output"))
    assert re.search(r"Output ONLY a JSON array", s)
    assert re.search(r"no Markdown fences", s)
    assert "`[]`" in s


def test_no_secrets_or_exploits_in_file():
    r = subprocess.run([sys.executable, str(GATE), "redact-check", "--paths", "agents"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([sys.executable, str(GATE), "redact-check", "--paths", str(AGENT)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr


def test_redact_check_catches_planted_secret(tmp_path):
    f = tmp_path / "agent.md"
    f.write_text(TEXT + "\nkey AKIAIOSFODNN7EXAMPLE\n")
    r = subprocess.run([sys.executable, str(GATE), "redact-check", "--paths", str(f)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode != 0


def test_rules_section_secret_and_exploit():
    s = flat(section(BODY, "Rules for findings"))
    assert re.search(r"Never print a secret value", s)
    assert re.search(r"file:line", s)
    assert re.search(r"No step-by-step exploitation", s)
    assert re.search(r"never a working exploit", s)
    assert not re.search(r"(?i)\bpayload\b|' OR 1=1|<script>|rm -rf", BODY)


def test_origin_header_follows_frontmatter():
    assert re.match(r"\s*<!-- \[origin ref=\S+ req=REQ-SECURITY-REVIEW-007", BODY)
    assert "[intent]" in BODY.split("[/origin]")[0]


def test_example_within_documented_length_limits():
    for ex in examples():
        for f in ex:
            assert len(f["threat"]) <= 400 and len(f["mitigation"]) <= 400
            for q in re.findall(r"«([^»]*)»", f["threat"]):
                assert len(q) <= 120
    assert len("x" * 401) > 400  # control: limit check is meaningful

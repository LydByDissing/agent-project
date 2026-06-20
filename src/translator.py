"""
Static Translator — converts DSL wire form to natural language using
expansion rules and templates. No LLM calls.

See docs/design/static-translator.md and docs/design/human-output.md
"""

from __future__ import annotations
from src.dsl_parser import DslNode, parse_dsl
from typing import Any


# ── Expansion Rules ──

def _expand_artifact(node: DslNode) -> str:
    path = node.get_attr("path")
    action = node.get_attr("action")
    lines = node.get_attr("lines", "")

    action_map = {
        "created": "Created",
        "modified": "Modified",
        "deleted": "Deleted",
    }
    verb = action_map.get(action, action.capitalize() if action else "Changed")

    if lines:
        return f"{verb} {path} ({lines} lines)"
    return f"{verb} {path}"


def _expand_added(node: DslNode) -> str:
    fn = node.get_attr("fn")
    in_type = node.get_attr("in")
    out_type = node.get_attr("out")
    if in_type and out_type:
        return f"Added {fn}({in_type}) -> {out_type}"
    return f"Added {fn}"


def _expand_removed(node: DslNode) -> str:
    fn = node.get_attr("fn")
    return f"Removed {fn}"


def _expand_verdict(node: DslNode) -> str:
    text = node.text.strip().lower()
    mapping = {
        "approve": "Approved",
        "request-changes": "Changes requested",
        "block": "Blocked",
    }
    return mapping.get(text, text.capitalize() if text else "Unknown verdict")


def _expand_finding(node: DslNode) -> str:
    severity = node.get_attr("severity", "info")
    path = node.get_attr("path", "")
    text = node.text.strip()
    loc = f" at {path}" if path else ""
    return f"{severity.capitalize()} finding{loc}: {text}"


def _expand_test_suite(node: DslNode) -> str:
    total = node.get_attr("total", "?")
    pass_count = node.get_attr("pass", "?")
    fail_count = node.get_attr("fail", "0")

    parts = [f"{pass_count} of {total} tests pass"]
    tests = node.children_by_tag("test")
    failures = [t for t in tests if t.get_attr("status") == "fail"]
    if failures:
        fail_parts = []
        for t in failures:
            name = t.get_attr("name", "unknown")
            reason = t.get_attr("reason", "no reason given")
            fail_parts.append(f"{name} failed: {reason}")
        parts.append(". " + ". ".join(fail_parts))
    return ", ".join(parts)


def _expand_error(node: DslNode) -> str:
    code = node.get_attr("code", "unknown")
    severity = node.get_attr("severity", "unknown")
    detail_node = node.child("detail")
    detail = detail_node.text.strip() if detail_node else ""
    if detail:
        return f"Error ({code}, {severity}): {detail}"
    return f"Error ({code}, {severity})"


def _expand_file(node: DslNode) -> str:
    path = node.get_attr("read") or node.get_attr("path", "unknown")
    return path


def _expand_complexity(node: DslNode) -> str:
    delta = node.get_attr("delta", "")
    return f"Complexity: {delta}"


def _expand_passthrough(node: DslNode) -> str:
    """Generic expansion for unknown/passthrough tags."""
    tag = node.tag
    status = node.get_attr("status", "")
    text = node.text.strip()
    if status and text:
        return f"{tag}: {status}. {text}"
    if status:
        return f"{tag}: {status}"
    if text:
        return f"{tag}: {text}"
    return f"{tag}: (empty)"


# ── Tag Expansion Registry ──

_TAG_EXPANDERS: dict[str, Any] = {
    "artifact": _expand_artifact,
    "added": _expand_added,
    "removed": _expand_removed,
    "verdict": _expand_verdict,
    "finding": _expand_finding,
    "test-suite": _expand_test_suite,
    "error": _expand_error,
    "file": _expand_file,
    "complexity": _expand_complexity,
}


def expand_node(node: DslNode) -> str:
    """Expand a single DSL node to an NL fragment."""
    expander = _TAG_EXPANDERS.get(node.tag)
    if expander:
        return expander(node)
    if node.passthrough or node.tag not in ("task", "result", "goal", "spec",
                                            "test-cases", "case", "focus",
                                            "context-ref", "output-artifact",
                                            "test", "note", "style",
                                            "security-check", "on-invalid",
                                            "field"):
        return _expand_passthrough(node)
    # Container tags — expand children
    child_texts = []
    for child in node.children:
        expanded = expand_node(child)
        if expanded:
            child_texts.append(expanded)
    return ". ".join(child_texts)


# ── Output Templates ──

CODER_TEMPLATE = """Code: {summary}. Files: {files}."""

REVIEWER_TEMPLATE = """Review: {verdict}. {findings}{security}"""

TESTER_TEMPLATE = """Tests: {test_summary}."""

AGGREGATE_TEMPLATE = """{coder_output}

{reviewer_output}

{tester_output}{action_items}"""


def _extract_coder_data(result: DslNode) -> dict[str, str]:
    """Extract coder-relevant data from a [result] node."""
    artifacts = result.children_by_tag("artifact")
    added = result.children_by_tag("added")
    removed = result.children_by_tag("removed")

    summary_parts = []
    for a in added:
        summary_parts.append(_expand_added(a))
    for r in removed:
        summary_parts.append(_expand_removed(r))

    files = ", ".join(_expand_artifact(a) for a in artifacts)

    return {
        "summary": ". ".join(summary_parts) if summary_parts else "No changes",
        "files": files,
    }


def _extract_reviewer_data(result: DslNode) -> dict[str, str]:
    """Extract reviewer-relevant data from a [result] node."""
    verdict_node = result.child("verdict")
    verdict = _expand_verdict(verdict_node) if verdict_node else "No verdict"

    findings = result.children_by_tag("finding")
    findings_text = ""
    if findings:
        findings_text = "Findings: " + ". ".join(_expand_finding(f) for f in findings)

    security_parts = []
    for child in result.children:
        if child.tag in ("security-check", "style"):
            expanded = expand_node(child)
            if expanded:
                security_parts.append(expanded)
    security_text = ". ".join(security_parts)

    return {
        "verdict": verdict,
        "findings": findings_text + ". " if findings_text else "",
        "security": security_text + ". " if security_text else "",
    }


def _extract_tester_data(result: DslNode) -> dict[str, str]:
    """Extract tester-relevant data from a [result] node."""
    suite = result.child("test-suite")
    if suite:
        test_summary = _expand_test_suite(suite)
    else:
        test_summary = "No test results"

    return {
        "test_summary": test_summary,
    }


# ── Public API ──

def dsl_to_nl(wire_form: str, agent_type: str) -> str:
    """Convert DSL wire form to natural language.

    Args:
        wire_form: DSL wire form string (a [result] message)
        agent_type: One of 'coder', 'reviewer', 'tester'

    Returns:
        Natural language string
    """
    result = parse_dsl(wire_form)
    if result.tag == "_root":
        # Find the [result] child
        for child in result.children:
            if child.tag == "result":
                result = child
                break

    if agent_type == "coder":
        data = _extract_coder_data(result)
        return CODER_TEMPLATE.format(**data)
    elif agent_type == "reviewer":
        data = _extract_reviewer_data(result)
        return REVIEWER_TEMPLATE.format(**data)
    elif agent_type == "tester":
        data = _extract_tester_data(result)
        return TESTER_TEMPLATE.format(**data)
    else:
        # Generic: expand all children
        return expand_node(result)


def aggregate_results(results: dict[str, str]) -> str:
    """Aggregate per-agent NL outputs into a single user-facing summary.

    Args:
        results: Dict mapping agent_type -> NL string
                 e.g. {"coder": "...", "reviewer": "...", "tester": "..."}

    Returns:
        Aggregated NL summary
    """
    coder_output = results.get("coder", "")
    reviewer_output = results.get("reviewer", "")
    tester_output = results.get("tester", "")

    # Detect action items
    action_items = []
    if tester_output and "fail" in tester_output.lower():
        action_items.append("test failures need attention")
    if reviewer_output and "changes requested" in reviewer_output.lower():
        action_items.append("review changes requested")

    action_items_text = ""
    if action_items:
        action_items_text = "\n\nNeeds attention: " + ", ".join(action_items)

    return AGGREGATE_TEMPLATE.format(
        coder_output=coder_output,
        reviewer_output=reviewer_output,
        tester_output=tester_output,
        action_items=action_items_text,
    )

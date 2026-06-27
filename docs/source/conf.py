project = "agent-project"
author = "Architecture Team"
release = "0.1.0"

extensions = ["sphinx_needs"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]

# sphinx-needs: custom types for SDD
needs_types = [
    dict(directive="feat", title="Feature", prefix="FEAT-", color="#BFD8D2", style="node"),
    dict(directive="req", title="Requirement", prefix="REQ-", color="#FEDCD2", style="node"),
    dict(directive="adr", title="Architecture Decision Record", prefix="ADR-", color="#DF744A", style="node"),
]

# Extra fields beyond the sphinx-needs defaults (sphinx-needs >= 2.0 dict format)
_str_field = {"schema": {"type": "string"}, "default": ""}
needs_fields = {
    "rationale":    {**_str_field, "description": "WHY this requirement or decision exists"},
    "acceptance":   {**_str_field, "description": "Testable criterion, copied verbatim into bd task [accept]"},
    "non_goal":     {**_str_field, "description": "What this requirement explicitly does NOT cover"},
    "c4_component": {**_str_field, "description": "C4 L3 component id that owns this requirement"},
    "c4_container": {**_str_field, "description": "C4 L2 container this component lives in"},
    "c4_scope":     {**_str_field, "description": "ADR: space-separated component/container ids, or 'system'"},
}

needs_id_required = True
needs_id_regex = "^(FEAT|REQ|ADR)-[A-Z0-9-]+"
needs_default_layout = "clean"

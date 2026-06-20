"""
DSL Serializer — converts structured data back to wire-form DSL.

Serialization rules (from message-schema.md section 6):
1. Attributes sorted alphabetically
2. Children in schema-defined order (core -> domain -> unknown)
3. Single-line output, no indentation
4. Enum values lowercase
5. Empty/omitted attributes not serialized
6. Text content stripped of leading/trailing whitespace
"""

from __future__ import annotations
from src.dsl_parser import DslNode, _needs_quoting
from typing import Any


def serialize_dsl(data: dict[str, Any]) -> str:
    """Serialize a dict (from DslNode.to_dict()) back to wire-form DSL."""
    node = _dict_to_node(data)
    return node.to_wire()


def serialize_node(node: DslNode) -> str:
    """Serialize a DslNode to wire-form DSL."""
    return node.to_wire()


def _dict_to_node(data: dict[str, Any]) -> DslNode:
    """Convert a plain dict to a DslNode."""
    tag = data.get("_tag", "_root")
    attrs = data.get("_attrs", {})
    text = data.get("_text", "")
    passthrough = data.get("_passthrough", False)

    children: list[DslNode] = []
    raw_children = data.get("_children", [])
    for child_data in raw_children:
        children.append(_dict_to_node(child_data))

    return DslNode(
        tag=tag,
        attrs=attrs,
        children=children,
        text=text.strip(),
        passthrough=passthrough,
    )

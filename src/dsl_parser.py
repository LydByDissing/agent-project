"""
DSL Parser — converts wire-form bracket-tag DSL into structured data.

Grammar (PEG-like):
  message   := tag*
  tag       := '[' name attr* ']' content '[' '/' name ']'
             | '[' name attr* ']' text '[' '/' name ']'
             | '[' name attr* '/' ']'          (self-closing, not used in PoC)
  attr      := key=value
             | key="quoted value"
  content   := text | tag*
  text      := any chars not starting with '['

Wire form is single-line, no whitespace between tags.
The parser is a recursive-descent parser with a simple tokenizer.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DslNode:
    """A parsed DSL node: tag name, attributes, children, and text."""
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[DslNode] = field(default_factory=list)
    text: str = ""
    passthrough: bool = False
    is_leaf: bool = False  # True if tag had no explicit close tag

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict for serialization."""
        d: dict[str, Any] = {"_tag": self.tag}
        if self.attrs:
            d["_attrs"] = dict(sorted(self.attrs.items()))
        if self.text:
            d["_text"] = self.text
        if self.children:
            d["_children"] = [c.to_dict() for c in self.children]
        if self.passthrough:
            d["_passthrough"] = True
        return d

    def to_wire(self) -> str:
        """Convert back to wire-form DSL."""
        parts = [f"[{self.tag}"]
        for k, v in sorted(self.attrs.items()):
            if _needs_quoting(v):
                parts.append(f' {k}="{v}"')
            else:
                parts.append(f" {k}={v}")
        parts.append("]")
        if self.text:
            parts.append(self.text)
            if not self.is_leaf:
                parts.append(f"[/{self.tag}]")
        elif self.children:
            for child in self.children:
                parts.append(child.to_wire())
            parts.append(f"[/{self.tag}]")
        return "".join(parts)

    def child(self, tag: str, index: int = 0) -> DslNode | None:
        """Find nth child by tag name."""
        matches = [c for c in self.children if c.tag == tag]
        if index < len(matches):
            return matches[index]
        return None

    def children_by_tag(self, tag: str) -> list[DslNode]:
        """Find all children by tag name."""
        return [c for c in self.children if c.tag == tag]

    def get_attr(self, key: str, default: str = "") -> str:
        return self.attrs.get(key, default)

    def __repr__(self) -> str:
        return f"<DslNode {self.tag} attrs={self.attrs}>"

    def to_pretty(self, indent: int = 0) -> str:
        """Pretty-print for debug/display."""
        pad = "  " * indent
        if not self.children and not self.text:
            attrs = " ".join(f'{k}="{v}"' if _needs_quoting(v) else f"{k}={v}"
                             for k, v in sorted(self.attrs.items()))
            return f"{pad}[{self.tag} {attrs}]" if attrs else f"{pad}[{self.tag}]"
        attrs = " ".join(f'{k}="{v}"' if _needs_quoting(v) else f"{k}={v}"
                         for k, v in sorted(self.attrs.items()))
        open_tag = f"{pad}[{self.tag} {attrs}]" if attrs else f"{pad}[{self.tag}]"
        if self.text:
            if self.is_leaf:
                return f"{open_tag}{self.text}"
            return f"{open_tag}{self.text}[/{self.tag}]"
        lines = [open_tag]
        for child in self.children:
            lines.append(child.to_pretty(indent + 1))
        lines.append(f"{pad}[/{self.tag}]")
        return "\n".join(lines)


def _needs_quoting(value: str) -> bool:
    """Check if a value needs quoting (contains spaces or special chars).
    Paths with / or : are fine unquoted. Only quote on spaces, brackets,
    quotes, or bare = that isnt part of a key=value.
    """
    if not value:
        return False
    if re.search(r'[\s\[\]"]', value):
        return True
    return False


# ── Tokenizer ──

_TOKEN_RE = re.compile(
    r"""
    \[/?              # opening bracket (start of open or close tag)
    [^\]]*            # tag name + attributes (everything until ])
    \]                # closing bracket
    |                 # OR
    [^\[]+            # plain text (anything not starting with [)
    """,
    re.VERBOSE,
)


def _tokenize(wire: str) -> list[str]:
    """Split wire form into tokens: tag-open, tag-close, text."""
    tokens = []
    pos = 0
    while pos < len(wire):
        m = _TOKEN_RE.match(wire, pos)
        if not m:
            raise DslParseError(f"Unexpected character at pos {pos}: {wire[pos:pos+20]!r}")
        token = m.group(0)
        if token.strip():
            tokens.append(token)
        pos = m.end()
    return tokens


# ── Parser ──

class DslParseError(Exception):
    pass


class _Parser:
    def __init__(self, wire: str):
        self.tokens = _tokenize(wire)
        self.pos = 0
        self._open_tags: list[str] = []

    def peek(self) -> str | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self) -> str:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def parse_nodes(self) -> list[DslNode]:
        """Parse a sequence of sibling nodes."""
        nodes = []
        while self.pos < len(self.tokens):
            token = self.peek()
            if token.startswith("[/"):
                # Close tag — let parent handle it
                break
            if token.startswith("["):
                nodes.append(self.parse_tag())
            else:
                # Bare text — create a text-only text node
                nodes.append(DslNode(tag="_text", text=self.advance()))
        return nodes

    def _has_close_tag(self, tag_name: str) -> bool:
        """Check if there is a [/<tag_name>] in the remaining tokens."""
        for i in range(self.pos, len(self.tokens)):
            if self.tokens[i] == f"[/{tag_name}]":
                return True
        return False

    def parse_tag(self) -> DslNode:
        """Parse [tagname attr=val ...]...[/tagname].

        Tags can be:
        - Container: [tag]content[/tag] — has explicit close tag
        - Leaf (no body): [tag attr=val] — no close tag in remaining tokens

        Leaf detection: if no [/<tag_name>] exists in remaining tokens,
        this is a leaf tag. All content between the open tag and the
        next sibling/close tag is the body.
        """
        open_token = self.advance()
        tag_name, attrs, implicit_text = self._parse_open_tag(open_token)

        # Determine if this is a leaf or container
        is_leaf = not self._has_close_tag(tag_name)

        if is_leaf:
            # Leaf tag: no children, no body to parse
            # implicit_text may hold content (e.g. [verdict approve])
            text = implicit_text
            node = DslNode(tag=tag_name, attrs=attrs, children=[], text=text, is_leaf=True)
            return node

        # Container tag: parse children until close tag
        self._open_tags.append(tag_name)
        children: list[DslNode] = []
        text: str = ""

        while self.pos < len(self.tokens):
            token = self.peek()
            if token == f"[/{tag_name}]":
                self.advance()
                self._open_tags.pop()
                break
            elif token.startswith("[/"):
                expected = self._open_tags[-1] if self._open_tags else "?"
                raise DslParseError(
                    f"Mismatched close tag: expected [/{expected}], got {token}"
                )
            elif token.startswith("["):
                children.append(self.parse_tag())
            else:
                text = self.advance()
        else:
            if self._open_tags:
                self._open_tags.pop()

        final_text = text.strip() if text.strip() else implicit_text
        node = DslNode(tag=tag_name, attrs=attrs, children=children, text=final_text)
        return node

    def _parse_open_tag(self, token: str) -> tuple[str, dict[str, str], str]:
        """Parse '[tagname key=val key="val with spaces"]' ->
        (name, {attrs}, text_content).

        If the attr part has no '=', it is treated as text content
        (e.g. [verdict approve] -> tag=verdict, text=approve).
        """
        inner = token[1:-1]  # strip [ and ]
        parts = inner.split(None, 1)  # first word is tag name
        tag_name = parts[0]
        attrs: dict[str, str] = {}
        text_content = ""
        if len(parts) > 1:
            attr_str = parts[1]
            if "=" in attr_str:
                attrs = self._parse_attrs(attr_str)
            else:
                # No '=' found — treat as text content
                text_content = attr_str
        return tag_name, attrs, text_content

    def _parse_attrs(self, s: str) -> dict[str, str]:
        """Parse 'key=val key2=val2' or 'key="val with spaces"'
        or 'key:val' (colon-separated shorthand).
        """
        attrs: dict[str, str] = {}
        i = 0
        while i < len(s):
            # Skip whitespace
            while i < len(s) and s[i] == " ":
                i += 1
            if i >= len(s):
                break
            # Read key — find next = or :
            eq_pos = s.find("=", i)
            colon_pos = s.find(":", i)
            if eq_pos == -1 and colon_pos == -1:
                # No more key=value pairs — rest is implicit text
                break
            if eq_pos == -1:
                eq_pos = len(s)
            if colon_pos == -1:
                colon_pos = len(s)
            sep_pos = min(eq_pos, colon_pos)
            sep_char = s[sep_pos]
            key = s[i:sep_pos]
            i = sep_pos + 1
            if i >= len(s):
                attrs[key] = ""
                break
            # Read value
            if s[i] == '"':
                # Quoted value
                close = s.index('"', i + 1)
                value = s[i + 1:close]
                attrs[key] = value
                i = close + 1
            else:
                # Unquoted value — read until space or end
                end = i
                while end < len(s) and s[end] != " ":
                    end += 1
                value = s[i:end]
                attrs[key] = value
                i = end
        return attrs


# ── Public API ──

def parse_dsl(wire: str) -> DslNode:
    """Parse a complete DSL message from wire form.

    Returns the root DslNode (which may be a [task], [result], etc.)
    For messages with a single top-level tag, returns that tag.
    For messages with multiple top-level tags, returns a synthetic root.
    """
    parser = _Parser(wire.strip())
    nodes = parser.parse_nodes()
    if len(nodes) == 1:
        return nodes[0]
    # Multiple top-level nodes — wrap in synthetic root
    return DslNode(tag="_root", children=nodes)


def parse_dsl_to_dict(wire: str) -> dict[str, Any]:
    """Parse DSL wire form and return a plain dict."""
    return parse_dsl(wire).to_dict()

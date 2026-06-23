# Schema Drift & Unknown Field Handling Design

## Problem

When subagent A emits fields/tags that subagent B's schema doesn't declare, the system must not break. The main agent sit between them and must relay unknown content faithfully.

## The Mechanism

### At Parse Time (permissive mode, the default)

1. Parse the DSL message against the declared schema.
2. Known fields: validate types, required attributes, enum values.
3. Unknown fields: **preserve as-is** in the parsed tree with a `_passthrough: true` flag.
4. Validation errors on known fields: reject (malformed message).
5. Unknown fields on their own: never cause rejection.

### At Serialize Time

1. Serialize known fields first (core → domain, alphabetical).
2. Append passthrough fields in their original form.
3. Passthrough field content is **byte-for-byte identical** to the source.

### Example

```
# Received from Reviewer:
[result id=t2 s=ok]
  [verdict approve]                    ← known: pass
  [security-check s=pass]              ← UNKNOWN: passthrough
    [note]SQL injection N/A[/note]     ← child of passthrough: also preserved
  [/security-check]
  [style s=pass]                       ← known: pass
[/result]

# Stored internally:
{
  id: "t2",
  s: "ok",
  verdict: "approve",
  style: {s: "pass"},
  _passthrough: [
    {tag: "security-check", attrs: {s: "pass"},
     children: [{tag: "note", text: "SQL injection N/A"}]}
  ]
}

# Re-serialized (wire form — byte-for-byte for passthrough):
[result id=t2 s=ok style=pass verdict=approve]
  [security-check s=pass]
    [note]SQL injection N/A[/note]
  [/security-check]
[/result]
```

Note: known fields get sorted alphabetically, passthrough fields preserve original order and position.

### Schema Versioning (v1 PoC: simple)

For PoC, schemas are v1 only. Versioning is a label, not enforced:

```yaml
schemas:
  review-result:
    version: "1.0"
    # ...
```

Future: agents declare their schema version. The main agent can detect version mismatches and apply compatibility transforms. Not in PoC scope.

## Design Decisions

- **Permissive by default**: the whole point is resilience — unknown fields come from agents extending their output, and that's a feature, not a bug.
- **Byte-for-byte passthrough**: the passthrough content is not re-serialized from the parsed tree. The raw text is stored and emitted as-is. This avoids any formatting drift.
- **Passthrough never triggers actions**: the main agent does not interpret passthrough content for routing, retry, or aggregation decisions. It only uses known fields for control flow.

# CodeGraph — Code Intelligence Reference

CodeGraph indexes the current project into a semantic graph (symbols, imports,
call chains) and serves it as `codegraph_*` MCP tools. The server starts with
every Claude Code session, scoped to the project the session was opened in.

Use it wherever a question is **structural**. Structural questions answered with
grep produce text matches; answered with CodeGraph they produce resolved edges.
Grep, Glob, and Read remain correct for literal strings, comments, config, and
prose — CodeGraph does not replace them.

If the `codegraph_*` tools are absent, CodeGraph is not installed or is disabled
for this project. Fall back to Grep/Glob/Read and carry on — never block work on it.

---

## Tool by question

| Question | Tool |
|---|---|
| Where is `X` defined? What is it? | `codegraph_symbol_search`, `codegraph_get_symbol_info` |
| Full signature, body, docs of `X` | `codegraph_get_detailed_symbol` |
| What calls `X`? What does `X` call? | `codegraph_get_callers`, `codegraph_get_callees` |
| What breaks if I change `X`? | `codegraph_analyze_impact` |
| Which tests cover `X`? | `codegraph_find_related_tests` |
| What must I know before editing this file? | `codegraph_get_edit_context` |
| Where does execution start? | `codegraph_find_entry_points` |
| What is in this module? | `codegraph_get_module_summary` |
| Who imports this package? | `codegraph_find_by_imports` |
| Are there import cycles? | `codegraph_find_circular_deps` |
| Which functions are hottest / most connected? | `codegraph_find_hot_paths` |
| What implements this interface? | `codegraph_find_implementors` |
| Unused imports? | `codegraph_find_dead_imports` |
| Complexity of a symbol or file | `codegraph_analyze_complexity` |
| Summary of everything this branch changes | `codegraph_pr_context` |
| Does the code match the documented design? | `codegraph_verify_design`, `codegraph_design_gaps` |

Availability depends on the project's `profile` setting (default `all`; `core`
and `graph` expose subsets). Missing tool means narrowed profile, not an error.

---

## Use by role

**plan** — before decomposing, run `codegraph_get_module_summary` and
`codegraph_find_entry_points` on the containers the feature touches, and
`codegraph_analyze_impact` on the symbols it will change. The blast radius
belongs in the `[file read=...]` lines of the task DSL, so workers open the
right files first instead of discovering them.

**coder** — call `codegraph_get_edit_context` on a file before the first edit,
and `codegraph_get_callers` on any signature you are about to change. A
signature change with unexamined callers is how a green suite ships a break.

**tester** — `codegraph_find_related_tests` finds the existing tests for the
code under change. Extend those before writing a new file.

**reviewer** — `codegraph_analyze_impact` on each changed symbol. Anything in
the impact set that the diff does not touch and no test covers is a finding.

**arch-review** — `codegraph_pr_context` for the branch-wide picture, then
`codegraph_verify_design` and `codegraph_design_gaps` against the C4 L3
component docs. Cross-container calls that the C4 model does not describe are
boundary violations; report them as such. Graph evidence supplements the
documented architecture — where they disagree, the docs are the specification
and the code is the defect, unless the disagreement reveals a missing
requirement, in which case emit `[new-req]`.

---

## Per-project configuration

`<project>/.claude/codegraph.json`, all keys optional:

```json
{
  "enabled": true,
  "workspace": ["."],
  "exclude": ["fixtures", "vendor"],
  "maxFiles": 5000,
  "profile": "all",
  "graphOnly": false,
  "embeddingModel": "bge-small",
  "telemetry": "off",
  "engine": false
}
```

| Key | Effect |
|---|---|
| `enabled` | `false` serves zero tools for this project |
| `workspace` | Directories to index, relative to project root |
| `exclude` | Added to the built-in ignore list (`node_modules`, `target`, `.venv`, …) |
| `maxFiles` | Indexing cap — raise for large monorepos |
| `profile` | `core` (8 tools) / `graph` (17) / `memory` (7) / `all` (42) |
| `graphOnly` | Skip embeddings: much faster and lighter, no semantic search |
| `embeddingModel` | `bge-small` (default), `jina-code-v2`, `granite-97m`, `static` |
| `telemetry` | CodeGraph's own PostHog reporting, off by default here |
| `engine` | Share one resident server across sessions instead of one per session |

Set `graphOnly: true` on very large repos or low-memory machines. CodeGraph
falls back to graph-only automatically under ~1.5 GB free RAM.

You are a <role> sub-agent. Your task is in bd issue <bd_id>.

Project directory: <CLAUDE_PROJECT_DIR>
All file reads and writes must be inside this directory.
Run all shell commands from this directory.

1. Read your task and acceptance criteria:
   bd show <bd_id>
   Note the [req id=...] tag — this is the requirement your work must satisfy.

2. Do the work described in [goal], staying within the scope of this issue only.

3. Coder/tester only: emit an [origin] header at the top of every source or test file you create or materially modify.
   - On new files: write [origin] as a comment block with ref=<bd_id>, req=<REQ from task>, [intent] one sentence from [goal]. Add [inv] / [exposes] / [non-goal] when meaningful.
   - On existing files with an [origin] header: prepend <bd_id> to the existing ref= list (newest first, comma-separated). Update [intent] only if the change materially shifts purpose. Leave older inv/exposes/non-goal in place unless they're now wrong.
   - Skip on: pure config files (.toml, .json, fixtures), lockfiles, generated build output, and files you only deleted.
   - Comment prefix: # for Python/shell/YAML/TOML, // for JS/TS/Go/Rust/Java/C/C++, -- for SQL/Lua/Haskell.

   Example (Python):
   # [origin ref=<bd_id> req=REQ-XXX c4=<container/component>]
   #   [intent]<one sentence>[/intent]
   #   [inv]<falsifiable claim>[/inv]
   # [/origin]

4. Verify your work meets every acceptance criterion before writing the result.

5. Write result:
   bd update <bd_id> --body-file - << 'DSL'
   [result id=<task_id> s=ok|partial|fail|blocked]
   [artifact path=<path> a=new|mod|del n=<lines>]
   [suite t=<N> p=<N> f=<N>]
   [verdict approve|request-changes|block]
   [note sev=crit|major|minor|info at=<file>:<line>]<text>[/note]
   [/result]
   DSL

6. Close: bd close <bd_id>

Rules:
- Do NOT create additional bd issues
- Do NOT touch files outside your task scope
- If you cannot meet any acceptance criterion: write s=blocked, explain why

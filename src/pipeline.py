"""
Level 3: Full Pipeline Runner with Real LLM Orchestration.

Two modes:
- Direct mode: Calls CLI agents (pi/Claude) directly via subprocess
- BD mode: Creates bd issues, agents pick them up from `bd ready`

In both cases, the main agent (LLM) decomposes NL input into DSL tasks,
and subagents (LLMs) produce DSL results.
"""

from __future__ import annotations
import subprocess
import json
import tiktoken
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

from src.dsl_parser import parse_dsl, DslParseError
from src.dsl_serializer import serialize_dsl
from src.translator import dsl_to_nl, aggregate_results
from src.process_loader import load_process, ProcessDefinition


# ── Data Structures ──

@dataclass
class PipelineMessage:
    msg_id: str
    from_agent: str
    to_agent: str
    raw_text: str          # Raw LLM output
    dsl_text: str          # Extracted DSL
    parsed: Any = None     # Parsed DslNode
    tokens: int = 0        # tiktoken count of dsl_text (DSL-content cost)
    usage: dict = field(default_factory=dict)  # CLI-reported wire usage


@dataclass
class PipelineResult:
    nl_output: str
    messages: list[PipelineMessage] = field(default_factory=list)
    total_tokens: int = 0
    dsl_tokens: int = 0
    nl_tokens: int = 0
    # Wire-level usage rolled up from CLI calls (when available).
    wire_input_tokens: int = 0
    wire_output_tokens: int = 0
    wire_cache_read_tokens: int = 0
    wire_cache_creation_tokens: int = 0
    success: bool = False
    errors: list[str] = field(default_factory=list)


# ── CLI Agent Interface ──

# Tools the Claude Code CLI exposes by default. DSL-only sub-agents need
# none of them; passing this list to --disallowed-tools shrinks the tool
# catalog the model conditions on.
_CLAUDE_TOOLS_TO_DISABLE = [
    "Bash", "BashOutput", "KillShell",
    "Read", "Write", "Edit", "NotebookEdit",
    "Glob", "Grep",
    "WebFetch", "WebSearch",
    "Task", "TodoWrite",
    "SlashCommand",
]


def call_agent(system_prompt: str, user_prompt: str,
               agent: str = "pi", model: str = "",
               timeout: int = 120,
               replace_system_prompt: bool = True,
               disable_tools: bool = True) -> tuple[str, bool, dict]:
    """Call a CLI agent in non-interactive mode.

    Args:
        system_prompt: Role prompt for the agent.
        user_prompt: User message.
        agent: "claude" or "pi".
        model: Optional model override.
        timeout: Seconds before subprocess is killed.
        replace_system_prompt: When True (and agent=claude), use --system-prompt
            (replaces the default preamble) instead of --append-system-prompt.
        disable_tools: When True (and agent=claude), disable the tool catalog
            via --disallowed-tools.

    Returns:
        (text, success, usage). `usage` is the CLI's reported token usage when
        --output-format json is used (claude path); empty dict otherwise.
    """
    usage: dict = {}

    if agent == "claude":
        cmd = ["claude", "--print", "--output-format", "json"]
        if replace_system_prompt:
            cmd.extend(["--system-prompt", system_prompt])
        else:
            cmd.extend(["--append-system-prompt", system_prompt])
        if model:
            cmd.extend(["--model", model])
        if disable_tools:
            cmd.append("--disallowed-tools")
            cmd.extend(_CLAUDE_TOOLS_TO_DISABLE)
        # Pass the user prompt via stdin so it doesn't collide with the
        # variadic --disallowed-tools list.
        try:
            result = subprocess.run(
                cmd, input=user_prompt,
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"CLI timeout (>{timeout}s)", False, usage
        except FileNotFoundError:
            return "claude CLI not found", False, usage

        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else "(no stderr)"
            return f"CLI error (exit {result.returncode}): {stderr}", False, usage

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            return f"CLI returned non-JSON ({e}): {result.stdout[:300]}", False, usage

        usage = payload.get("usage", {}) or {}
        if payload.get("is_error"):
            return (f"CLI reported error: {payload.get('api_error_status', 'unknown')}",
                    False, usage)
        return (payload.get("result", "") or "").strip(), True, usage

    if agent == "pi":
        cmd = ["pi", "--print", "--append-system-prompt", system_prompt]
        if model:
            cmd.extend(["--model", model])
        cmd.append(user_prompt)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return f"CLI timeout (>{timeout}s)", False, usage
        except FileNotFoundError:
            return "pi CLI not found", False, usage
        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else "(no stderr)"
            return f"CLI error (exit {result.returncode}): {stderr}", False, usage
        return result.stdout.strip(), True, usage

    return f"Unknown agent: {agent}", False, usage


def count_tokens(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


# ── Prompt Construction ──

def build_main_agent_prompt(process: ProcessDefinition) -> str:
    """Build the main agent's system prompt — decompose-only.

    Aggregation is static (src/translator.py), so the main agent never sees a
    Phase-3 prompt. Keep this prompt to: a one-line role, the sub-agent roster
    (label + description + accepted task types), one task example, and the
    output rule.
    """
    workers = []
    for aid, adef in process.agents.items():
        if adef.role == "orchestrator":
            continue
        types = ", ".join(t.replace("-task", "") for t in adef.input_schemas)
        workers.append(f"  {aid} (type={types}): {adef.description}")
    roster = "\n".join(workers)

    return (
        "You orchestrate sub-agents. Decompose the user's request into one "
        "[task] DSL message per sub-agent that should run, then stop.\n"
        "\n"
        "Sub-agents:\n"
        f"{roster}\n"
        "\n"
        "Task shape (one line, no whitespace between tags):\n"
        "[task id=<id> type=<type>]"
        "[goal]<what>[/goal]"
        "[file read=<path>]"
        "[spec]<inline structured spec>[/spec]"
        "[context-ref id=<other-task.artifacts>]"
        "[/task]\n"
        "\n"
        "Use [context-ref id=tN.artifacts] to reference a prior task's outputs "
        "instead of re-sending files. Sub-agents derive output paths from the "
        "spec — do not pre-specify them.\n"
        "\n"
        "Output ONLY [task] messages. No prose, no markdown fence.\n"
    )


# Per-agent output cheat sheet. Each agent sees only the tags it actually
# emits — no generic DSL syntax block, no input schema, no foreign tags.
# Keep in sync with translator expanders in src/translator.py.
_AGENT_OUTPUT_EXAMPLES: dict[str, str] = {
    "coder": (
        "[result id=<task-id> s=ok|partial|fail]"
        "[artifact a=new|mod|del n=<lines> path=<path>]"
        "[added fn=<name> in:<type> out:<type>]"
        "[complexity delta=<+Ncyclomatic>]"
        "[/result]"
    ),
    "reviewer": (
        "[result id=<task-id> s=ok|partial|fail]"
        "[note sev=crit|major|minor|info at=<file>:<line>]<finding>[/note]"
        "[security-check s=pass|fail][note]<detail>[/note][/security-check]"
        "[style s=pass|fail|warn]"
        "[verdict approve|request-changes|block]"
        "[/result]"
    ),
    # In [suite], list ONLY failing tests as [test] children; pass count is in
    # the suite attrs. This keeps suites with many tests cheap.
    "tester": (
        "[result id=<task-id> s=ok|partial|fail]"
        "[artifact a=new n=<lines> path=<path>]"
        "[suite t=<total> p=<pass> f=<fail>]"
        "[test name=<name> s=fail reason=<why>]"
        "[/suite]"
        "[/result]"
    ),
}


def build_subagent_prompt(process: ProcessDefinition, agent_id: str) -> str:
    """Build a sub-agent's system prompt.

    Minimal by design: role line, hard rule, single-line example showing only
    the tags this agent emits. The task message itself shows the input format.
    """
    adef = process.agents[agent_id]
    example = _AGENT_OUTPUT_EXAMPLES.get(
        agent_id, "[result id=<task-id> s=ok|partial|fail][/result]"
    )
    return (
        f"You are the {adef.label}. {adef.description}\n"
        f"Emit exactly one [result] DSL message. No prose, no markdown fence, "
        f"no whitespace between tags.\n"
        f"Shape: {example}\n"
    )


# ── DSL Extraction ──

def extract_dsl(text: str, start_tag: str = "[result") -> str:
    """Extract DSL from LLM output. Handles markdown fences and extra text."""
    t = text.strip()

    # Remove markdown code fences
    if t.startswith("```"):
        lines = t.split("\n")
        t = "\n".join(lines[1:-1]) if len(lines) > 2 else t
        t = t.strip()

    # Find the start tag
    idx = t.find(start_tag)
    if idx == -1:
        return t  # Return as-is for error reporting

    # Find the matching close tag
    close_tag = "[/" + start_tag[1:]  # [result -> [/result
    end_idx = t.rfind(close_tag)
    if end_idx == -1:
        return t[idx:]

    return t[idx:end_idx + len(close_tag)]


# ── Pipeline Runner ──

def run_pipeline(process_path: str, user_input: str,
                 agent: str = "pi", model: str = "",
                 aggregate: str = "static",
                 verbose: bool = False) -> PipelineResult:
    """Run the full multi-agent pipeline with real LLM calls.

    Args:
        process_path: Path to process.yaml
        user_input: Natural language input from user
        agent: CLI agent to use ("pi" or "claude")
        model: Model name (optional)
        aggregate: "static" uses src.translator (free, deterministic).
                   "llm" calls the main agent to synthesize the summary.
        verbose: Print intermediate outputs

    Returns:
        PipelineResult with NL output, messages, and token counts
    """
    result = PipelineResult(nl_output="")

    # Load process definition
    try:
        process = load_process(process_path)
    except Exception as e:
        result.errors.append(f"Failed to load process: {e}")
        return result

    main_agent = None
    for aid, adef in process.agents.items():
        if adef.role == "orchestrator":
            main_agent = adef
            break

    if not main_agent:
        result.errors.append("No orchestrator agent defined")
        return result

    # ── Phase 1: Main Agent decomposes user input into DSL tasks ──
    if verbose:
        print("=" * 60)
        print("PHASE 1: Main Agent — NL to DSL decomposition")
        print("=" * 60)

    main_prompt = build_main_agent_prompt(process)

    if verbose:
        print(f"\nSystem prompt ({count_tokens(main_prompt)} tokens):")
        print(main_prompt[:300] + "...")
        print(f"\nUser input: {user_input}")

    raw_output, success, main_usage = call_agent(
        main_prompt, user_input, agent=agent,
        model=main_agent.model or model,
    )

    if not success:
        result.errors.append(f"Main agent LLM call failed: {raw_output}")
        return result

    _accumulate_usage(result, main_usage)

    if verbose:
        print(f"\nMain agent output:\n{raw_output[:500]}")

    # Parse task messages from main agent output
    task_messages = _extract_tasks(raw_output)

    if not task_messages:
        result.errors.append("Main agent did not produce any [task] messages")
        result.errors.append(f"Raw output: {raw_output[:300]}")
        return result

    if verbose:
        print(f"\nExtracted {len(task_messages)} task(s):")
        for tid, ttext in task_messages.items():
            print(f"  {tid}: {ttext[:100]}...")

    # Record main agent messages
    for tid, ttext in task_messages.items():
        try:
            parsed = parse_dsl(ttext)
        except DslParseError as e:
            result.errors.append(f"Task {tid} failed to parse: {e}")
            parsed = None

        msg = PipelineMessage(
            msg_id=tid,
            from_agent="main",
            to_agent=parsed.get_attr("type", "unknown") if parsed else "unknown",
            raw_text=ttext,
            dsl_text=ttext,
            parsed=parsed,
            tokens=count_tokens(ttext),
        )
        result.messages.append(msg)
        result.dsl_tokens += msg.tokens

    # ── Phase 2: Dispatch tasks to subagents (wave-by-wave concurrent) ──
    if verbose:
        print("\n" + "=" * 60)
        print("PHASE 2: Subagent execution")
        print("=" * 60)

    waves = _dependency_waves(task_messages)
    if verbose:
        for i, w in enumerate(waves):
            print(f"  wave {i}: {', '.join(w)}")

    subagent_results: dict[str, str] = {}  # task_id -> DSL result

    for wave in waves:
        # Tasks in the same wave have no cross-dependencies, so dispatch
        # concurrently. Each worker returns a self-contained outcome dict;
        # we merge into the shared result sequentially after the wave.
        with ThreadPoolExecutor(max_workers=len(wave)) as pool:
            outcomes = list(pool.map(
                lambda tid: _dispatch_subagent(
                    process, tid, task_messages[tid],
                    agent=agent, fallback_model=model, verbose=verbose,
                ),
                wave,
            ))

        for outcome in outcomes:
            if outcome.get("error"):
                result.errors.append(outcome["error"])
                continue
            _accumulate_usage(result, outcome["usage"])
            subagent_results[outcome["tid"]] = outcome["dsl_result"]
            result.messages.append(outcome["message"])
            result.dsl_tokens += outcome["message"].tokens

    # ── Phase 3: Aggregate results → NL ──
    if verbose:
        print("\n" + "=" * 60)
        print(f"PHASE 3: Aggregation — DSL to NL (mode={aggregate})")
        print("=" * 60)

    if aggregate == "static":
        nl_output = _aggregate_static(result)
    elif aggregate == "llm":
        nl_output, llm_ok = _aggregate_llm(
            result, agent=agent, model=main_agent.model or model,
        )
        if not llm_ok:
            result.errors.append(f"Aggregation LLM call failed: {nl_output}")
            result.errors.append("Fell back to static aggregation")
            nl_output = _aggregate_static(result)
    else:
        result.errors.append(f"Unknown aggregate mode: {aggregate!r} (using static)")
        nl_output = _aggregate_static(result)

    result.nl_output = nl_output
    result.nl_tokens = count_tokens(nl_output)
    result.total_tokens = result.dsl_tokens + result.nl_tokens
    result.success = len([m for m in result.messages if m.to_agent == "main"]) > 0

    if verbose:
        print(f"\nNL Output ({result.nl_tokens} tokens):\n{nl_output}")

    return result


def _dispatch_subagent(process: ProcessDefinition, tid: str, ttext: str,
                       agent: str, fallback_model: str,
                       verbose: bool = False) -> dict:
    """Run one sub-agent call. Returns a self-contained outcome dict so the
    caller can merge into shared state sequentially. Thread-safe: touches
    no shared state except via the returned dict.
    """
    try:
        parsed = parse_dsl(ttext)
    except DslParseError as e:
        return {"tid": tid, "error": f"Task {tid} failed to parse for dispatch: {e}"}

    agent_type = parsed.get_attr("type", "")

    target_agent = None
    for aid, adef in process.agents.items():
        if adef.role == "worker" and agent_type in adef.input_schemas:
            target_agent = aid
            break
    if not target_agent:
        # Fallback: match by schema name containing the type.
        for aid, adef in process.agents.items():
            if adef.role == "worker":
                for sname in adef.input_schemas:
                    if agent_type in sname:
                        target_agent = aid
                        break
            if target_agent:
                break
    if not target_agent:
        return {"tid": tid, "error": f"No agent found for task type: {agent_type}"}

    if verbose:
        goal = parsed.child("goal")
        goal_text = goal.text.strip() if goal else ""
        print(f"  → {tid} → {target_agent} (type={agent_type}): {goal_text[:80]}")

    sub_prompt = build_subagent_prompt(process, target_agent)
    sub_adef = process.agents[target_agent]

    sub_output, success, sub_usage = call_agent(
        sub_prompt, ttext, agent=agent,
        model=sub_adef.model or fallback_model,
    )
    if not success:
        return {"tid": tid, "error": f"Subagent {target_agent} failed: {sub_output}",
                "usage": sub_usage}

    dsl_result = extract_dsl(sub_output, "[result")
    try:
        result_parsed = parse_dsl(dsl_result)
    except DslParseError as e:
        if verbose:
            print(f"  ✗ {tid} parse error: {e}")
        result_parsed = None

    msg = PipelineMessage(
        msg_id=f"{tid}-result",
        from_agent=target_agent,
        to_agent="main",
        raw_text=sub_output,
        dsl_text=dsl_result,
        parsed=result_parsed,
        tokens=count_tokens(dsl_result),
        usage=sub_usage,
    )
    return {
        "tid": tid,
        "dsl_result": dsl_result,
        "message": msg,
        "usage": sub_usage,
    }


def _dependency_waves(task_messages: dict[str, str]) -> list[list[str]]:
    """Group tasks into waves; tasks in the same wave have no cross-dependencies.

    Dependencies are derived from [context-ref id=tN.<...>] children — a task
    that references t1 must run after t1 completes. Returns topological levels;
    tasks in level k can run concurrently.
    """
    deps: dict[str, set[str]] = {tid: set() for tid in task_messages}
    for tid, ttext in task_messages.items():
        try:
            parsed = parse_dsl(ttext)
        except DslParseError:
            continue
        for cref in parsed.children_by_tag("context-ref"):
            ref_id = cref.get_attr("id", "")
            base = ref_id.split(".", 1)[0]
            if base and base in task_messages and base != tid:
                deps[tid].add(base)

    waves: list[list[str]] = []
    remaining = {tid: set(d) for tid, d in deps.items()}
    while remaining:
        ready = sorted(tid for tid, d in remaining.items() if not d)
        if not ready:
            # Cycle or unresolved dep — run everything left as one final wave
            # rather than dropping work. Caller still sees outputs.
            waves.append(sorted(remaining.keys()))
            break
        waves.append(ready)
        for tid in ready:
            remaining.pop(tid)
        for d in remaining.values():
            d.difference_update(ready)
    return waves


def _aggregate_static(result: PipelineResult) -> str:
    """Aggregate sub-agent results into NL using src.translator.

    Free and deterministic — no LLM call. Maps each result message to the
    NL form for its originating agent, then templates them together.
    """
    per_agent_nl: dict[str, str] = {}
    for r in result.messages:
        if r.to_agent != "main" or not r.parsed:
            continue
        per_agent_nl[r.from_agent] = dsl_to_nl(r.dsl_text, r.from_agent)
    return aggregate_results(per_agent_nl)


def _aggregate_llm(result: PipelineResult, agent: str, model: str) -> tuple[str, bool]:
    """Aggregate via an LLM call to the main agent."""
    results_text = "\n\n".join(
        f"Result from {r.from_agent} ({r.msg_id}):\n{r.dsl_text}"
        for r in result.messages
        if r.to_agent == "main"
    )

    aggregation_prompt = f"""## ROLE: Main Orchestrator Agent (Aggregation Phase)

You have received results from subagents in LLM-DSL format.
Synthesize them into a coherent natural language response for the user.

### SUBAGENT RESULTS

{results_text}

### YOUR TASK
Write a natural language summary for the user covering:
1. What each subagent did
2. Key findings, issues, or concerns
3. Files changed
4. Any action items needing user attention

Be concise but informative. Use bullet points or sections for clarity.
"""

    text, ok, usage = call_agent(
        aggregation_prompt,
        "Please synthesize the subagent results into a user-facing summary.",
        agent=agent,
        model=model,
    )
    _accumulate_usage(result, usage)
    return text, ok


def _accumulate_usage(result: PipelineResult, usage: dict) -> None:
    """Roll a single CLI `usage` dict into the result totals."""
    if not usage:
        return
    result.wire_input_tokens += usage.get("input_tokens", 0) or 0
    result.wire_output_tokens += usage.get("output_tokens", 0) or 0
    result.wire_cache_read_tokens += usage.get("cache_read_input_tokens", 0) or 0
    result.wire_cache_creation_tokens += usage.get("cache_creation_input_tokens", 0) or 0


def _extract_tasks(text: str) -> dict[str, str]:
    """Extract [task] messages from main agent output.

    Returns dict of task_id -> task_dsl_text.
    """
    tasks = {}
    t = text.strip()

    # Remove markdown fences
    if t.startswith("```"):
        lines = t.split("\n")
        t = "\n".join(lines[1:-1]) if len(lines) > 2 else t
        t = t.strip()

    # Find all [task ...]...[/task] blocks
    idx = 0
    while True:
        start = t.find("[task ", idx)
        if start == -1:
            break

        # Find the matching [/task]
        end_tag = "[/task]"
        end = t.find(end_tag, start)
        if end == -1:
            break

        task_text = t[start:end + len(end_tag)]

        # Extract task ID
        id_match = task_text.split("id=", 1)
        if len(id_match) > 1:
            task_id = id_match[1].split(" ")[0].split("]")[0]
            tasks[task_id] = task_text

        idx = end + len(end_tag)

    return tasks

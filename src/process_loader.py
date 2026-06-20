"""
Process Definition Loader — loads and validates process.yaml files.

See docs/design/agent-process.md
"""

from __future__ import annotations
import yaml
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path


@dataclass
class SchemaField:
    name: str
    field_type: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: dict[str, Any] = field(default_factory=dict)
    enum_values: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class SchemaDef:
    name: str
    extends: str = "core"
    fields: dict[str, SchemaField] = field(default_factory=dict)
    enums: dict[str, list[str]] = field(default_factory=dict)
    description: str = ""
    version: str = "1.0"


@dataclass
class AgentDef:
    agent_id: str
    role: str  # "orchestrator" or "worker"
    label: str = ""
    description: str = ""
    system_prompt: str = ""
    input_schemas: list[str] = field(default_factory=list)
    output_schemas: list[str] = field(default_factory=list)
    validation: str = "permissive"
    max_retries: int = 3
    context_budget: int = 3000


@dataclass
class Route:
    from_agent: str
    to_agents: list[str]
    messages: list[str]


@dataclass
class CompositionStep:
    step_id: str
    agent_id: str = ""
    task_schema: str = ""
    pattern: str = "single"  # single, parallel, pipeline, conditional, loop, aggregate
    context_from: str = ""
    on_finish: str = "end"
    on_fail: str = "abort"
    steps: list[CompositionStep] = field(default_factory=list)
    evaluate: str = ""
    sources: list[str] = field(default_factory=list)
    branches: dict[str, str] = field(default_factory=dict)
    max_iterations: int = 3


@dataclass
class ProcessDefinition:
    name: str
    version: str = "1.0"
    schemas: dict[str, SchemaDef] = field(default_factory=dict)
    agents: dict[str, AgentDef] = field(default_factory=dict)
    routes: list[Route] = field(default_factory=list)
    composition: CompositionStep | None = None
    dag: DagComposition | None = None
    raw: dict[str, Any] = field(default_factory=dict)


# ── DAG Composition (new) ──

@dataclass
class DagTask:
    task_id: str
    agent_type: str = ""
    schema: str = ""
    depends_on: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    fan_in: str = "all"
    when: str = ""
    retries: int = 0
    body: str = ""
    acceptance: list[str] = field(default_factory=list)

@dataclass
class DagComposition:
    tasks: list[DagTask] = field(default_factory=list)
    defaults: dict[str, str] = field(default_factory=dict)

    def ready_tasks(self, completed: set[str]) -> list[DagTask]:
        """Return tasks whose dependencies are all met."""
        return [
            t for t in self.tasks
            if t.task_id not in completed
            and all(d in completed for d in t.depends_on)
        ]

    def topo_sort(self) -> list[DagTask]:
        """Topological sort of tasks by dependency order."""
        visited: set[str] = set()
        result: list[DagTask] = []
        task_map = {t.task_id: t for t in self.tasks}

        def visit(tid: str):
            if tid in visited:
                return
            visited.add(tid)
            task = task_map.get(tid)
            if task:
                for dep in task.depends_on:
                    visit(dep)
                result.append(task)

        for t in self.tasks:
            visit(t.task_id)

        return result


class ProcessLoadError(Exception):
    pass


def load_process(path: str | Path) -> ProcessDefinition:
    """Load and validate a process.yaml file."""
    path = Path(path)
    if not path.exists():
        raise ProcessLoadError(f"Process file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ProcessLoadError("Process file must be a YAML mapping")

    name = raw.get("process")
    if not name:
        raise ProcessLoadError("Missing 'process' name")

    version = raw.get("version", "1.0")

    proc = ProcessDefinition(name=name, version=version, raw=raw)

    # Load schemas
    schemas_block = raw.get("schemas", {})
    proc.schemas = _load_schemas(schemas_block)

    # Load agents
    agents_block = raw.get("agents", {})
    proc.agents = _load_agents(agents_block)

    # Validate: exactly one orchestrator
    orchestrators = [a for a in proc.agents.values() if a.role == "orchestrator"]
    if len(orchestrators) != 1:
        raise ProcessLoadError(
            f"Expected exactly 1 orchestrator, found {len(orchestrators)}"
        )

    # Load topology
    topology_block = raw.get("topology", {})
    proc.routes = _load_routes(topology_block)
    _validate_routes(proc)

    # Load composition (old nested format)
    comp_block = raw.get("composition", {})
    if comp_block:
        if comp_block.get("type") == "dag":
            proc.dag = _load_dag_composition(comp_block)
        else:
            proc.composition = _load_composition(comp_block)
            _validate_composition(proc)

    return proc


def _load_schemas(block: dict[str, Any]) -> dict[str, SchemaDef]:
    schemas: dict[str, SchemaDef] = {}
    for name, data in block.items():
        if not isinstance(data, dict):
            continue
        sd = SchemaDef(
            name=name,
            extends=data.get("extends", "core"),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
        )
        # Load enums
        enums_block = data.get("enums", {})
        for enum_name, values in enums_block.items():
            if isinstance(values, list):
                sd.enums[enum_name] = values
        # Load fields
        fields_block = data.get("fields", {})
        for field_name, field_def in fields_block.items():
            if isinstance(field_def, dict):
                sf = SchemaField(
                    name=field_name,
                    field_type=field_def.get("type", "str"),
                    description=field_def.get("description", ""),
                )
                if "attrs" in field_def:
                    sf.attrs = field_def["attrs"]
                if "children" in field_def:
                    sf.children = field_def["children"]
                if "values" in field_def:
                    sf.enum_values = field_def["values"]
                sd.fields[field_name] = sf
        schemas[name] = sd
    return schemas


def _load_agents(block: dict[str, Any]) -> dict[str, AgentDef]:
    agents: dict[str, AgentDef] = {}
    for agent_id, data in block.items():
        if not isinstance(data, dict):
            continue
        schema = data.get("schema", {})
        ad = AgentDef(
            agent_id=agent_id,
            role=data.get("role", "worker"),
            label=data.get("label", agent_id),
            description=data.get("description", ""),
            system_prompt=data.get("system-prompt", ""),
            input_schemas=_ensure_list(schema.get("input", [])),
            output_schemas=_ensure_list(schema.get("output", [])),
            validation=data.get("validation", "permissive"),
            max_retries=data.get("max-retries", 3),
            context_budget=data.get("context-budget", 3000),
        )
        agents[agent_id] = ad
    return agents


def _load_routes(block: dict[str, Any]) -> list[Route]:
    routes: list[Route] = []
    routes_list = block.get("routes", [])
    for r in routes_list:
        if not isinstance(r, dict):
            continue
        from_agent = r.get("from", "")
        to_agents = _ensure_list(r.get("to", []))
        messages = _ensure_list(r.get("messages", []))
        if isinstance(from_agent, list):
            for fa in from_agent:
                routes.append(Route(from_agent=fa, to_agents=to_agents, messages=messages))
        else:
            routes.append(Route(from_agent=from_agent, to_agents=to_agents, messages=messages))
    return routes


def _validate_routes(proc: ProcessDefinition) -> None:
    agent_ids = set(proc.agents.keys())
    for route in proc.routes:
        if route.from_agent not in agent_ids:
            raise ProcessLoadError(
                f"Route references unknown agent: {route.from_agent}"
            )
        for to in route.to_agents:
            if to not in agent_ids:
                raise ProcessLoadError(
                    f"Route references unknown agent: {to}"
                )


def _load_composition(block: dict[str, Any], prefix: str = "") -> CompositionStep:
    pattern = block.get("pattern", "single")
    step = CompositionStep(
        step_id=prefix or "root",
        pattern=pattern,
        evaluate=block.get("evaluate", ""),
        on_finish=block.get("on-finish", "end"),
        on_fail=block.get("on-fail", "abort"),
        max_iterations=block.get("max-iterations", 3),
    )

    if "sources" in block:
        step.sources = _ensure_list(block["sources"])

    if "branches" in block:
        step.branches = block["branches"]

    steps_list = block.get("steps", [])
    for i, s in enumerate(steps_list):
        if not isinstance(s, dict):
            continue
        sub = CompositionStep(
            step_id=s.get("id", f"step-{i}"),
            agent_id=s.get("agent", ""),
            task_schema=s.get("task", ""),
            context_from=s.get("context-from", ""),
            on_finish=s.get("on-finish", "end"),
            on_fail=s.get("on-fail", "abort"),
            pattern=s.get("pattern", "single"),
        )
        # Nested composition
        if "steps" in s:
            sub.pattern = s.get("pattern", "single")
            for j, sub_s in enumerate(s.get("steps", [])):
                if isinstance(sub_s, dict):
                    sub.steps.append(CompositionStep(
                        step_id=sub_s.get("id", f"sub-step-{j}"),
                        agent_id=sub_s.get("agent", ""),
                        task_schema=sub_s.get("task", ""),
                        context_from=sub_s.get("context-from", ""),
                        on_finish=sub_s.get("on-finish", "end"),
                        on_fail=sub_s.get("on-fail", "abort"),
                    ))
        step.steps.append(sub)

    return step


def _validate_composition(proc: ProcessDefinition) -> None:
    if not proc.composition:
        return
    agent_ids = set(proc.agents.keys())
    _validate_steps(proc.composition.steps, agent_ids)


def _validate_steps(steps: list[CompositionStep], agent_ids: set[str]) -> None:
    step_ids: set[str] = set()
    for step in steps:
        if step.step_id in step_ids:
            raise ProcessLoadError(f"Duplicate step ID: {step.step_id}")
        step_ids.add(step.step_id)
        if step.agent_id and step.agent_id not in agent_ids:
            raise ProcessLoadError(
                f"Step '{step.step_id}' references unknown agent: {step.agent_id}"
            )
        if step.steps:
            _validate_steps(step.steps, agent_ids)


def _ensure_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []

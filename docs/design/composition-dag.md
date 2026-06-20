# DAG Composition — Mapped to BD Molecules

## Key Insight

`bd` already has a DAG composition model: **formulas → molecules**.

- Formula (`.formula.json`): defines a DAG of steps with `depends_on`
- `bd cook`: compiles formula into a proto (template)
- `bd mol pour`: instantiates proto as a molecule (real issues)
- `bd ready`: fan-in (all blockers resolved)
- `bd mol progress`: tracking

We don't build a new composition engine. We **use bd's**.

## Mapping

| Our Concept | BD Concept |
|-------------|------------|
| Process definition | Formula (`.formula.json`) |
| Agent type | Issue label (`agent=coder`) |
| Task dispatch | `bd mol pour` (spawns molecule) |
| Task message | Issue body in DSL format |
| Result message | Issue body update in DSL format |
| Dependencies | `depends_on` in formula → `blocks` in bd |
| Fan-in | `bd ready` (all blockers resolved) |
| Composition flow | `bd mol progress` (tracking) |

## Formula File Format

A `.formula.json` is the process definition:

```json
{
  "formula": "code-review-pipeline",
  "description": "Implement code change with review and testing",
  "variables": {
    "task_description": {"required": true},
    "files_to_read": {"required": true},
    "output_files": {"required": true}
  },
  "steps": [
    {
      "id": "implement",
      "title": "Implement: {{task_description}}",
      "agent": "coder",
      "body": "[task type=code][goal]{{task_description}}[/goal]..."
    },
    {
      "id": "review",
      "title": "Review: {{task_description}}",
      "agent": "reviewer",
      "depends_on": ["implement"],
      "body": "[task type=review]..."
    },
    {
      "id": "test",
      "title": "Test: {{task_description}}",
      "agent": "tester",
      "depends_on": ["implement"],
      "body": "[task type=test]..."
    },
    {
      "id": "aggregate",
      "title": "Aggregate: {{task_description}}",
      "agent": "main",
      "depends_on": ["review", "test"],
      "body": "[task type=aggregate]..."
    }
  ]
}
```

## Workflow

### 1. Define Formula

Create `.formula.json` in `.beads/formulas/`:

```bash
# Create the formula file (one-time setup)
cat > .beads/formulas/code-review-pipeline.formula.json << 'JSON'
{
  "formula": "code-review-pipeline",
  "steps": [...]
}
JSON
```

### 2. Cook Formula (compile to proto)

```bash
bd cook .beads/formulas/code-review-pipeline.formula.json --persist
# → Creates proto (template) with DAG structure
```

### 3. Pour Molecule (spawn work)

```bash
bd mol pour code-review-pipeline \
  --var task_description="Add input validation to POST /users" \
  --var files_to_read="src/handlers/user.py" \
  --var output_files="src/handlers/user.py,src/validation/user_schema.py"
# → Creates real issues with DSL bodies and dependencies
```

### 4. Agents Work

```bash
# Agent picks up ready work
bd ready --label "agent=coder"
# → Shows implement task (no deps)

# Agent reads task DSL
bd show llm-dsl-xxx

# Agent does work, updates body with result DSL
bd update llm-dsl-xxx --body-file - << 'DSL'
[result id=t1 status=complete]
[artifact type=file path=src/handlers/user.py action=modified lines=+23]
[added fn=validate_user_input in:RequestBody out:ValidationResult]
[/result]
DSL

# Agent closes task
bd close llm-dsl-xxx

# Review and test auto-unblock (dependencies met)
bd ready --label "agent=reviewer"
bd ready --label "agent=tester"
```

### 5. Track Progress

```bash
bd mol progress llm-dsl-mol-root-id
# → Progress: 2 / 4 (50.0%)
```

## What BD Handles Natively

| Feature | BD Command | Behavior |
|---------|------------|----------|
| DAG dependencies | `depends_on` in formula | `blocks` edges between issues |
| Fan-in (all) | `bd ready` | Shows issues with all blockers resolved |
| Blocked tracking | `bd blocked` | Shows issues with open blockers |
| Progress tracking | `bd mol progress` | Percent complete |
| Auto-close | `bd close` | Molecule auto-closes when all steps done |
| Dependency types | `--type blocks\|tracks\|related\|parent-child` | Rich dependency semantics |
| Cycle detection | `bd dep cycles` | Detects circular dependencies |
| Dependency graph | `bd dep tree` | Shows full dependency tree |
| Bulk wiring | `bd dep add --file deps.jsonl` | Bulk dependency creation |

## What We Build on Top

BD handles the DAG structure. We add:

1. **DSL validation**: Validate issue bodies contain valid DSL
2. **Agent routing**: Map `agent=coder` label to the right subagent prompt
3. **Summary generation**: Main agent reads DSL results, produces summary
4. **Token counting**: Measure DSL vs NL token usage
5. **Error handling**: Propagate failures through the DAG

## Implementation

```python
from src.bd_runner import BdPipelineRunner

runner = BdPipelineRunner()

# Cook formula (one-time)
runner.cook_formula("code-review-pipeline.formula.json")

# Pour molecule (per task)
mol_id = runner.pour_molecule("code-review-pipeline", {
    "task_description": "Add input validation",
    "files_to_read": "src/handlers/user.py",
})

# Monitor progress
runner.wait_for_molecule(mol_id)

# Collect results and summarize
results = runner.collect_molecule_results(mol_id)
summary = runner.synthesize(results)
```

# [origin ref=llm-dsl-n1g3 req=REQ-TRACER-BULLETS-001 c4=sdd_skills/conductor]
#   [intent]Doc-contract: worker result writes append to notes and never replace the task brief.[/intent]
# [/origin]
import re
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parent.parent
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))
RESULT_WRITE = re.compile(r"bd update <bd_id>[^\n]*")

@pytest.mark.doc_contract
@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_skill_result_writes_use_append_notes(path):
    writes = RESULT_WRITE.findall(path.read_text())
    assert all("--append-notes" in w for w in writes), f"{path}: {writes}"

@pytest.mark.doc_contract
def test_conductor_and_implement_have_result_writes_to_check():
    names = {p.parent.name for p in SKILLS if RESULT_WRITE.search(p.read_text())}
    assert {"conductor", "implement"} <= names

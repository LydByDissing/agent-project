# [origin ref=llm-dsl-gu1y.18 req=REQ-OPERATOR-EDU-004,REQ-OPERATOR-EDU-010 c4=sdd_skills/plan_skill]
#   [intent]Registers the doc_contract marker so prose checks on SKILL.md and README are visibly separated from behaviour tests and never raise an unknown-marker warning.[/intent]
# [/origin]


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "doc_contract: asserts an instruction is present inside its SKILL.md section; prose-level, not behaviour",
    )

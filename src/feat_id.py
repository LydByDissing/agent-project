# [origin ref=llm-dsl-yms.3 req=REQ-GITHUB-ISSUES-002 c4=sdd_skills/sdd_orchestrator]
#   [intent]Derive a FEAT-XXX identifier from a GitHub issue title.[/intent]
# [/origin]

import re


def derive_feat_id(title: str, max_chars: int = 20) -> str:
    slug = re.sub(r'[^a-z0-9 -]', '', title.lower())
    slug = re.sub(r'\s+', '-', slug).strip('-')
    if len(slug) > max_chars:
        slug = slug[:max_chars]
        last = slug.rfind('-')
        if last > 0:
            slug = slug[:last]
    return f"FEAT-{slug.upper()}"

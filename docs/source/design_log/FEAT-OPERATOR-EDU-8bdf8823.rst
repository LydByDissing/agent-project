FEAT-OPERATOR-EDU Design Session — run 8bdf8823
================================================

:Date: 2026-11-21
:Feature: FEAT-OPERATOR-EDU
:Run: 8bdf8823
:c4_elements: learn_app learn_server learn_spa lesson_library lesson_selector question_generator plan_skill conductor sdd_skills
:Requirements: FEAT-OPERATOR-EDU REQ-OPERATOR-EDU-001 REQ-OPERATOR-EDU-002 REQ-OPERATOR-EDU-003 REQ-OPERATOR-EDU-004 REQ-OPERATOR-EDU-005 REQ-OPERATOR-EDU-006 REQ-OPERATOR-EDU-007 REQ-OPERATOR-EDU-008 REQ-OPERATOR-EDU-009 REQ-OPERATOR-EDU-010 REQ-OPERATOR-EDU-011

Interview Transcript
--------------------

**User** (brief): Bring education into the SDD workflow. With agentic coding
the developer loses track of the details. While sub-agents work, the
operator moves on to another task or doom-scrolls. Present on-topic
educational content during the wait, then a few multiple-choice questions,
and store the results in a local state file so that content the developer
already knows well is not shown again. List sources so it is easy to read
more. It should be a dynamic website next to the source, not the shell. It
is fine to store the content in the project repo. Sphinx diagrams are
great, but Sphinx may not be dynamic enough.

**Agent**: Presented the shared parts (content in the repo with mandatory
sources, the plan phase tags topics, the conductor writes ``now.json``, the
state is in ``.sdd/learner.json`` with spaced repetition) and three delivery
options: (A) Sphinx with a quiz directive, (B) a live local server, (C)
Sphinx-authored content plus a live server. Also asked whether to teach
general concepts or project-specific knowledge.

**User**: We likely need multiple lessons per topic, since something like
IaC is a very large topic. We also need to ask the dev about their
interest. I like backend code but do not care much about CSS, so I would
usually not want to go deep on CSS details.

**Agent**: Proposed a domain → topic → lesson-series hierarchy with levels
(intro / working / deep) and prerequisites, and an interest profile
(deep / basics / skip) set at onboarding and changed with buttons on each
lesson. Generation follows interest, and skip domains get only a one-line
"what changed" note.

**User**: The learning content must live in its own folder and should not
be linked to the docs site. They serve different purposes and people.
Create a new ``learn`` folder.

**Agent**: What should lessons teach? How should the page get the
operator's attention? Which stack? When should missing lessons be generated?

**User**: Generic content that can be updated on each run. Questions must
be personalised from the local state file and the dev's knowledge level.
Auto-open a browser tab. Leaning towards a Node/Vite SPA, since advanced or
rich diagram support is needed, but diagrams could also be rendered by
Claude and used as images. Generate during the plan phase.

**Agent**: How should questions be personalised (a tiered bank or live
generation)? How should diagrams be produced? Which backend?

**User**: Generated live per dev. Source plus pre-rendered SVG. Vite plus a
small Node server.

**Agent**: How should the server call Claude: headless ``claude -p``, an
API key, or auto-detect?

**User**: Headless ``claude -p``.

**Agent**: Presented the docs for approval.

**User**: The state needs to be somewhere in ``~/``. Otherwise approve.

Design Decisions
----------------

- **Storage**: top-level ``learn/``, never linked from Sphinx (ADR-001).
- **Structure**: domain / topic / ordered lessons with levels and
  prerequisites (REQ-001).
- **Sources**: mandatory per lesson and cited per question (REQ-002, -008).
- **Learner state**: ``~/.sdd/learner.json``, shared across projects and
  never committed. Run status ``now.json`` stays in the project (REQ-005).
- **Interest**: deep / basics / skip, set at onboarding and inline (REQ-006).
- **Stack**: Vite SPA + Hono server shipped in the plugin (ADR-002).
- **Questions**: live per operator via ``claude -p``, no bank (ADR-003).
- **Diagrams**: source plus committed SVG (ADR-004).
- **Trigger**: the plan phase generates lessons. The conductor writes
  ``now.json`` and auto-opens the browser (REQ-004, -010).
- **Defaults chosen by the agent** (open to change): port 4747, Leitner
  intervals 0/1/2/4/8/16 days, 3 questions per quiz, ``SDD_LEARN=off`` to
  disable, and committed SPA build so operators need only ``node``.

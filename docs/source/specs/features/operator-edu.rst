Operator Education — Learn While the Agents Work
================================================

.. feat:: Operator Education — Learn While the Agents Work
   :id: FEAT-OPERATOR-EDU
   :status: approved

   With agentic coding the operator (the developer driving ``/sdd``) loses
   contact with the details: sub-agents write the code while the operator
   switches task or scrolls. This feature turns the waiting time into
   learning time. When the conductor spawns a wave, a local learning web app
   opens beside the source and shows a short lesson on a topic the running
   jobs touch. Lessons are generic, sourced, and stored in a top-level
   ``learn/`` folder in the project repo, so they are generated once and
   refreshed on later runs instead of being regenerated each time. After the
   lesson, Claude generates a few multiple-choice questions for this
   operator, based on their learner state. Each answer updates a state file
   in the operator's home directory (``~/.sdd/``) holding their interest
   and mastery per topic. The state follows the person across projects.
   Knowing Terraform state in one repo means knowing it in the next. Content the operator already knows well, or has said they do not
   care about, is not shown again.

   The ``learn/`` library is separate from the Sphinx docs site. They serve
   different purposes and different readers (see ADR-001).

Requirements
------------

.. req:: Learn library in a top-level learn/ folder, organised as domain / topic / lesson
   :id: REQ-OPERATOR-EDU-001
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: Large subjects (e.g. IaC) cannot fit in one lesson. A
       three-level hierarchy with ordered, prerequisite-linked lessons lets
       the library grow in depth without becoming one huge page. Keeping it
       outside ``docs/`` separates teaching material from the project's
       specification (ADR-001).
   :acceptance: Given ``learn/iac/terraform-state/01-what-state-is.md`` and
       ``learn/iac/terraform-state/02-remote-backends.md`` where 02 declares
       ``requires: [iac/terraform-state/01-what-state-is]``, when the library
       loader runs, then it returns domain ``iac``, topic
       ``terraform-state``, two lessons in order, with levels and the
       prerequisite edge. A lesson whose ``requires`` names a missing lesson
       makes the loader fail and name the missing id. Nothing under
       ``docs/source`` references ``learn/``.
   :non_goal: No authoring UI. Lessons are files edited by the plan phase
       or by hand. No cross-project shared library.
   :c4_component: lesson_library
   :c4_container: learn_app

   The system shall store learning content under ``<project>/learn/`` as
   ``<domain>/<topic>/<NN>-<slug>.md`` files. Each file has YAML front matter
   with ``id``, ``title``, ``level`` (``intro`` | ``working`` | ``deep``),
   ``requires`` (list of lesson ids, may be empty), ``sources`` and
   ``updated`` (ISO date), followed by a Markdown body. Each domain and
   topic directory has an ``index.yaml`` with a title and summary.

.. req:: Every lesson lists its sources
   :id: REQ-OPERATOR-EDU-002
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: The operator must be able to read further and to check the
       generated content. An unsourced lesson cannot be trusted or
       followed up.
   :acceptance: Given a lesson whose ``sources`` list is empty, or has an
       entry with neither ``url`` nor ``path``, when ``learn validate`` runs,
       then it exits non-zero and names the lesson file and the bad entry.
       Given a valid lesson, the SPA shows a "Sources" section with each
       entry as a link (URL) or a repo-relative ``path[:line]`` reference.
   :non_goal: Does not check that URLs are reachable at validation time.
   :c4_component: lesson_library
   :c4_container: learn_app

   The system shall require at least one source per lesson. Each source has
   a ``title`` and either a ``url`` or a repo-relative ``path`` (with an
   optional line). The validator shall reject lessons that break this rule,
   and the SPA shall show the sources with every lesson.

.. req:: Diagrams kept as source plus pre-rendered SVG
   :id: REQ-OPERATOR-EDU-003
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: Lessons need rich diagrams (C4, sequence, infra topology).
       Rendering at generation time allows any diagram tool (PlantUML, D2,
       Mermaid) and keeps the SPA a plain image viewer (ADR-004).
   :acceptance: Given ``learn/iac/terraform-state/diagrams/state-flow.puml``
       and a lesson body referencing ``diagrams/state-flow.svg``, when the
       plan phase generates or updates the lesson, then the committed SVG
       sits next to its source. ``learn validate`` fails if a referenced SVG
       is missing or older than its source. The SPA shows the SVG with
       zoom and pan.
   :non_goal: No diagram rendering in the browser. No interactive diagram
       editing.
   :c4_component: lesson_library
   :c4_container: learn_app

   The system shall store each lesson diagram as source
   (``.puml`` | ``.d2`` | ``.mmd``) next to a committed SVG rendered from it.
   Lessons shall reference only the SVG.

.. req:: Plan phase tags jobs with topics and generates or refreshes lessons
   :id: REQ-OPERATOR-EDU-004
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: The plan phase already knows which C4 elements, ADRs and
       technologies each job touches, so it is the cheapest place to decide
       what is on topic. Generating before implement means lessons are ready
       when the waves start.
   :acceptance: Given a plan whose job touches a Terraform module, when the
       plan skill emits the ``[exec]`` block, then that job carries
       ``topics=iac/terraform-state``. If that topic has no lesson at or
       below the deepest level any interest setting allows, the plan phase
       writes one and commits it in the plan commit. An existing lesson
       older than its sources' newest change, or flagged ``stale: true``, is
       revised and gets a new ``updated`` date. Topics set to ``skip`` in
       ``learner.json`` get no lessons generated.
   :non_goal: Does not generate quiz questions (REQ-OPERATOR-EDU-008).
       Does not add a user approval gate. Lesson generation must not block
       the plan gate.
   :c4_component: plan_skill
   :c4_container: sdd_skills

   The system shall extend the Plan Skill to add a ``topics=`` attribute
   (domain/topic ids) to each ``[exec]`` job, and to create or refresh the
   lessons for those topics in ``learn/`` up to the depth allowed by the
   operator's interest settings.

.. req:: Local learner state file
   :id: REQ-OPERATOR-EDU-005
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: Knowledge and interests belong to the person, not to the
       repo. Keeping them in the home directory means they are never
       committed and carry over between projects, since lessons are generic
       and keyed by stable ``domain/topic/slug`` ids. One versioned JSON
       file keeps the server stateless and lets the operator inspect or
       reset their progress.
   :acceptance: Given no ``~/.sdd/learner.json``, when the learn server
       starts, then it creates the file with ``schema: 1``, empty
       ``interest``, ``mastery`` and ``history``. ``SDD_LEARN_HOME``
       overrides ``~/.sdd``. A file with an unknown ``schema`` value makes
       the server refuse to start and name the version it found. Given two
       learn servers for two projects, when both record an answer, then
       neither write is lost: each write re-reads, merges and renames
       atomically. Nothing learner-related is written inside the project.
   :non_goal: No sync across machines. No multi-user server. Run status
       (``now.json``) is not learner state and stays in the project
       (REQ-OPERATOR-EDU-010).
   :c4_component: learn_server
   :c4_container: learn_app

   The system shall persist per-operator learning state in
   ``~/.sdd/learner.json`` (or ``$SDD_LEARN_HOME/learner.json``), shared by
   all projects: ``interest`` per domain or topic
   (``deep`` | ``basics`` | ``skip``), ``mastery`` per lesson (Leitner box
   0–5 plus ``due`` date), and an append-only ``history`` of answered
   questions (lesson id, question summary, chosen and correct option,
   timestamp).

.. req:: Interest onboarding and inline interest adjustment
   :id: REQ-OPERATOR-EDU-006
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: Operators care about different things. One operator wants
       backend depth and no CSS detail. Without an interest profile the app
       wastes the waiting time on unwanted material.
   :acceptance: Given a ``learner.json`` with no interest entries, when the
       SPA opens, then it shows an onboarding screen listing the domains in
       ``learn/``, each settable to deep / basics / skip, and saves the
       choices. Given a lesson on screen, when the operator clicks "not for
       me", then that topic's interest becomes ``skip`` and the next lesson
       is selected. A topic-level setting overrides its domain-level
       setting.
   :non_goal: Does not infer interest from behaviour. Interest changes only
       when the operator sets it.
   :c4_component: learn_spa
   :c4_container: learn_app

   The system shall ask for the operator's interest per domain on first use,
   offer "more like this / basics are enough / not for me" controls on
   every lesson, and provide a settings view to change any domain or topic
   interest later.

.. req:: On-topic lesson selection weighted by interest and mastery
   :id: REQ-OPERATOR-EDU-007
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: The lesson shown should relate to what the agents are doing
       now, match the operator's interest depth, and avoid material they
       already know, while known material still comes back for review.
   :acceptance: Given ``now.json`` listing active topics
       ``[backend/http-caching, frontend/css-grid]``, interest
       ``backend: deep, frontend: skip``, and no mastery, when ``GET
       /api/next`` is called, then it returns the first ``backend/http-caching``
       lesson whose prerequisites are mastered (box ≥ 3), plus a
       ``what_changed`` note for ``frontend/css-grid`` with no lesson. A
       ``basics`` topic only yields ``intro`` lessons. A lesson at box 5
       that is not due is never returned. With no active topics, a due
       review lesson is returned. Selection is deterministic for a given
       state and date.
   :non_goal: No machine-learned ranking. No selection across projects.
   :c4_component: lesson_selector
   :c4_container: learn_app

   The system shall pick the next lesson by filtering on interest depth
   and satisfied prerequisites, then ranking by (active topic in
   ``now.json``, due for review, lowest mastery box, lesson order), with
   ties broken by lesson id.

.. req:: Personalised multiple-choice questions generated live with claude -p
   :id: REQ-OPERATOR-EDU-008
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: Fixed question banks soon test things the operator already
       knows or miss what they got wrong. Generating per operator, from
       their mastery and past mistakes, keeps the questions at their level.
       The headless Claude Code CLI uses the operator's existing login and
       needs no extra API key (ADR-003).
   :acceptance: Given a lesson and a ``learner.json`` showing two earlier
       misses on that lesson, when the SPA opens the lesson, then the server
       starts ``claude -p`` in the background with the lesson body, the
       operator's box and level, and the missed question summaries. It
       parses JSON with 3 questions, each with 3–5 options, one correct
       index, an explanation per option, and a ``source`` that matches one
       of the lesson's sources. Output that fails the schema, or cites a
       source not in the lesson, is rejected and the SPA shows the error
       with a retry button. It never shows placeholder questions. Without
       ``claude`` on PATH, the server names the missing binary.
   :non_goal: No Anthropic SDK or API-key path. Lessons are not generated
       here.
   :c4_component: question_generator
   :c4_container: learn_app

   The system shall generate quiz questions on demand by calling
   ``claude -p --output-format json`` with a prompt built from the lesson
   and the operator's learner state, validate the result against the
   question schema, and start generation while the lesson is still being
   read to hide the latency.

.. req:: Answers update mastery
   :id: REQ-OPERATOR-EDU-009
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: Mastery must follow actual performance so that known
       content drops out and weak content returns.
   :acceptance: Given a lesson at box 2, when the operator answers all
       questions correctly, then it moves to box 3 with ``due`` = today + 4
       days. Any wrong answer drops it to box 1 with ``due`` = tomorrow.
       Each answer is appended to ``history`` with the explanation and
       source shown to the operator. Box intervals are 0, 1, 2, 4, 8 and 16
       days for boxes 0–5.
   :non_goal: No SM-2 or FSRS scheduling in this version.
   :c4_component: learn_server
   :c4_container: learn_app

   The system shall record each quiz answer in ``learner.json`` and move
   the lesson between Leitner boxes using the fixed interval table, with
   today's date passed in as a parameter.

.. req:: Conductor publishes wave status and opens the learn app
   :id: REQ-OPERATOR-EDU-010
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: The learn app must know what is running to stay on topic,
       and the operator must be pulled toward it at the moment they would
       otherwise drift off.
   :acceptance: Given an ``[exec]`` block with topic-tagged jobs, when the
       conductor spawns wave 0, then it writes ``<project>/.sdd/now.json``
       (gitignored; run id,
       wave number, per-job id, title, topics, status). If the learn server
       is not answering on its port, it starts it, then opens the browser at
       the learn URL once per run. As each worker returns, the job status in
       ``now.json`` changes to done or failed, and the SPA shows the wave
       progress within 5 seconds. When ``SDD_LEARN=off`` is set, none of
       this happens.
   :non_goal: The conductor never waits on the learn app. If the server
       fails to start, the conductor logs one line and carries on.
   :c4_component: conductor
   :c4_container: sdd_skills

   The system shall make the conductor write wave and job status to
   ``.sdd/now.json`` at each wave start and job completion, start the learn
   server if it is not running, and open the operator's browser on the
   first wave of a run.

.. req:: Learn server and SPA
   :id: REQ-OPERATOR-EDU-011
   :links: FEAT-OPERATOR-EDU
   :status: approved
   :rationale: A dynamic app is needed to write state, follow wave progress
       and run quizzes. The static Sphinx site cannot do this (ADR-002).
   :acceptance: Given ``learn-app/`` shipped in the plugin, when
       ``node learn-app/server.js --project <dir>`` runs, then it binds to
       ``127.0.0.1`` only, on port ``SDD_LEARN_PORT`` (default 4747), serves
       the built Vite SPA, and exposes ``GET /api/now``, ``GET /api/next``,
       ``GET /api/lesson/:id``, ``POST /api/quiz/:lessonId``, ``POST
       /api/answer``, and ``GET``/``PUT /api/interest``. A request for a
       lesson id outside ``learn/`` returns 404. The server reads only the
       project's ``learn/`` and ``.sdd/now.json`` and the learner home
       (``~/.sdd``).
   :non_goal: No authentication (localhost only). No hosted deployment.
   :c4_component: learn_server
   :c4_container: learn_app

   The system shall provide a Node (Hono) server and a Vite-built SPA,
   shipped in the plugin under ``learn-app/``, that serves the project's
   ``learn/`` library, its ``.sdd/now.json`` and the operator's
   ``~/.sdd/learner.json`` on localhost.

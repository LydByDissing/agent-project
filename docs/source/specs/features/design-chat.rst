Design Phase Chat Capture
=========================

.. feat:: Design Phase Chat Capture
   :id: FEAT-DESIGN-CHAT
   :status: draft

   Captures the full conversational transcript of the SDD docs phase interview
   as a searchable RST artifact stored in ``docs/source/design_log/``. Each
   transcript is tagged with the C4 element IDs and requirement IDs produced
   during that session. Developers can search design history by component or
   requirement when revisiting decisions — without the discussion ever being
   fed back into pipeline context.

Requirements
------------

.. req:: Design log RST written after docs interview
   :id: REQ-DESIGN-CHAT-001
   :links: FEAT-DESIGN-CHAT
   :status: draft
   :rationale: Design discussions contain rationale, rejected alternatives,
       and implicit constraints that become critical context when requirements
       change. Storing them durably prevents loss when context resets or
       sessions end.
   :acceptance: Given docs phase complete for FEAT-XXX with run ID RRR, the
       file ``docs/source/design_log/FEAT-XXX-RRR.rst`` exists and contains
       the full Q&A transcript of the docs interview (agent questions and user
       answers, in order) before the approval gate is presented to the user.
   :non_goal: Does not capture plan, implement, or arch-review phase
       conversations. Does not summarise or interpret the transcript content.
   :c4_component: docs_skill
   :c4_container: sdd_skills

   The system shall write a human-readable RST transcript of the docs phase
   interview to ``docs/source/design_log/FEAT-XXX-RRR.rst`` after the
   interview is complete and before the user approval gate is presented.
   The transcript must include every agent question and every user answer in
   chronological order.

.. req:: Transcript tagged with C4 element IDs and requirement IDs
   :id: REQ-DESIGN-CHAT-002
   :links: FEAT-DESIGN-CHAT
   :status: draft
   :rationale: Tags enable grep-based discovery across all design logs.
       When a component's requirements change, a developer can search the
       design_log for that component ID to find every session that touched it.
   :acceptance: The RST file header contains a ``:c4_elements:`` field
       listing every C4 component id and container id written during the
       session, and a ``:requirements:`` field listing every REQ-XXX-NNN and
       FEAT-XXX written. Running ``grep -r "<component_id>"
       docs/source/design_log/`` returns the file.
   :non_goal: Does not auto-extract tags from transcript prose. Tags are
       derived only from the sphinx-needs items written during the session —
       not from LLM parsing of the conversation text.
   :c4_component: docs_skill
   :c4_container: sdd_skills

   The system shall include in the design log RST header a ``:c4_elements:``
   field (space-separated component and container ids) and a
   ``:requirements:`` field (space-separated FEAT-XXX and REQ-XXX-NNN ids)
   covering everything written during that docs phase run.

.. req:: Design log indexed in Sphinx site
   :id: REQ-DESIGN-CHAT-003
   :links: FEAT-DESIGN-CHAT
   :status: draft
   :rationale: Browsability from the Sphinx site lets developers discover
       design history without needing shell access or a separate search tool.
   :acceptance: ``docs/source/design_log/index.rst`` exists with a toctree
       listing all design log entries. ``make html`` builds without error.
       The entry for FEAT-XXX-RRR appears in the index after the docs phase
       for that run completes.
   :non_goal: Does not implement a diff view between sessions. Does not
       implement full-text search beyond what Sphinx's built-in search
       provides.
   :c4_component: docs_skill
   :c4_container: sdd_skills

   The system shall maintain ``docs/source/design_log/index.rst`` with a
   toctree that includes every design log RST file. The entry for the current
   run is added (appended to the toctree) when the design log file is written.

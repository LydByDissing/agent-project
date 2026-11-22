ADR-003: Quiz questions are generated live through headless claude -p
=====================================================================

.. adr:: Quiz questions are generated live through headless claude -p
   :id: ADR-003
   :status: accepted
   :c4_scope: question_generator

   **Context**: Questions must be personalised to the operator's mastery
   and past mistakes, which only the local ``learner.json`` knows.

   **Decision**: The learn server shells out to ``claude -p --output-format
   json`` for each quiz, with a prompt built from the lesson and the learner
   state. No question bank is stored.

   **Rationale**: Uses the operator's existing Claude Code login and plan,
   so there is no API key to manage. Live generation adapts to every
   answer.

   **Consequences**: Each quiz takes several seconds, hidden by starting
   generation while the lesson is read. Tokens are spent per quiz. The
   ``claude`` binary must be on PATH. Output must be schema-validated
   because the CLI returns free text wrapped in JSON.

   **Alternatives considered**:

   - Tiered question bank picked adaptively: rejected. Not personal enough.
   - Anthropic SDK with an API key: rejected. Extra credential and separate
     billing.

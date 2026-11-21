ADR-002: Learn app is a Vite SPA served by a small Node (Hono) server
=====================================================================

.. adr:: Learn app is a Vite SPA served by a small Node (Hono) server
   :id: ADR-002
   :status: accepted
   :c4_scope: learn_app learn_server learn_spa

   **Context**: The learn app must render rich lessons, run quizzes, show
   live wave progress, and read and write files in ``.sdd/``.

   **Decision**: A Vite-built SPA served by one Node process (Hono) that
   also exposes a small JSON API. It ships in the plugin under
   ``learn-app/`` with its build output committed, so operators need only
   ``node`` and no ``npm install``.

   **Rationale**: Gives the richest UI path. One process serves both the
   SPA and the state API. Hono is small and has few dependencies.

   **Consequences**: Adds a JS toolchain to a Python-heavy plugin. Tests for
   ``learn-app/`` run with Vitest. The plugin's Python test suite does not
   cover it. ``node`` becomes a soft requirement: with ``SDD_LEARN=off`` the
   pipeline works without it.

   **Alternatives considered**:

   - Python server + htmx: rejected. The operator wants a richer UI.
   - Python API + Vite SPA: rejected. Two runtimes for one small tool.
   - Vite dev-server middleware: rejected. It would always run in dev mode.

# Decisions

Architectural decisions and tradeoffs, one short entry each. Newest at the bottom.

<!--
## D-NNN: Title
**Context:** what forced a choice.
**Decision:** what we chose.
**Alternatives:** what we didn't choose, and why.
-->

## D-001: src layout
**Context:** Where the package lives relative to the repo root.
**Decision:** `src/counterwrench/`. Tests can only import the installed package, so packaging mistakes surface locally instead of on a reviewer's fresh clone.
**Alternatives:** Flat layout (`counterwrench/` at root) is simpler, but tests can pass by importing local files that wouldn't ship.

## D-002: Dependencies arrive with the step that uses them
**Context:** The full stack (LangGraph, LangChain providers, Postgres drivers, FastAPI...) is known up front.
**Decision:** Each build step adds only what it needs, so every dependency in the lockfile traces to a specific step and reason.
**Alternatives:** Installing everything in step 1 is faster, but the lockfile becomes unexplainable.

## D-003: Make as the task runner, real targets only
**Context:** Reviewers expect `make up`, `make eval`; development happens on Windows.
**Decision:** Keep a Makefile with single-command recipes (`uv run ...`, `docker compose ...`) that work under sh, cmd and PowerShell. A target is added only when it works.
**Alternatives:** `just` (nicer syntax, but an extra install for reviewers); a Python task script (cross-platform, but nonstandard).

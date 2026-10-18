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

## D-004: Config loads `.env` into the process environment
**Context:** LangChain providers and LangSmith read API keys and tracing flags from `os.environ`.
**Decision:** `python-dotenv` loads `.env` into the environment (real env vars win), and model resolution is a pure function of that mapping. All model IDs and defaults live in `config.py`; `.env.example` shows the official pinned config as comments. OpenRouter goes through the official `langchain-openrouter` integration, whose `openrouter_provider` parameter handles pinning, instead of `langchain-openai` with a swapped base URL.
**Alternatives:** `pydantic-settings` is typed, but it doesn't export values to the environment, which would leave two sources of truth.

## D-005: Judge family is the model's maker, not the API
**Context:** Cross-family judging reduces self-preference bias, and OpenRouter serves many families through one key.
**Decision:** The family comes from the model's maker (`openrouter:anthropic/...` is Anthropic). A blank judge setting picks the first strong candidate from a different family than the agent; OpenRouter alone can provide that. Same family is a last resort and logs a warning. Official config: Haiku 5.5 agent, GPT-6.1 Sol judge, both via OpenRouter, with the provider order pinned to `anthropic,openai`. Reviewers with an Anthropic key auto-detect to the same agent model directly.
**Alternatives:** Treating each API provider as a family would call an OpenRouter-served Claude judge "cross-family" against a direct Claude agent. A cheaper DeepSeek agent would surface more failures, but less proven tool calling would add noise.

## D-006: Doctor verifies the serving backend, and fails closed
**Context:** Pinning is configured in `.env`, but a configured setting can be dropped between `.env` and the HTTP request (e.g. a library upgrade renaming the parameter) without any error. LangChain's response metadata doesn't say which OpenRouter backend served a call.
**Decision:** Doctor looks up each call in OpenRouter's generation-stats endpoint and fails if the backend is outside the pinned order or can't be confirmed. The same lookup reports the dated snapshot (e.g. `claude-haiku-5.5-20261007`), which experiments should record so a silent model swap is visible.
**Alternatives:** Trusting the config (misses dropped parameters). Warning instead of failing on an unconfirmed backend: friendlier to reviewers when OpenRouter's stats are slow, but an unverified pin would pass a check meant to certify reproducibility.

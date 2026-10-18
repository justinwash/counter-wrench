# AI usage

How the coding assistant helped, and what Justin checked himself.

<!--
## Step N: Title
**Assistant did:**
**Justin checked / decided:**
-->

## Step 1: Repo scaffold
**Assistant did:** Proposed the scaffold (src layout, per-step dependencies, Make with single-command recipes, ruff rule set), installed uv and GNU Make via winget on the Windows dev machine, wrote the files, and ran the checks (install on Python 3.12, lint, smoke test, `.env` ignored).
**Justin checked / decided:** Approved the proposal as written; explained back the scaffold, `.env` vs `.env.example`, Python version pinning, and lockfile vs `pyproject.toml` ranges.

## Step 1b: Model config module
**Assistant did:** Checked current LangChain packages (found the official `langchain-openrouter` integration, replacing the plan's base-URL approach), researched current model IDs, pricing and tool/structured-output support across providers and OpenRouter backends, wrote `config.py` and its 22 tests.
**Justin checked / decided:** Approved splitting the plan's step 1b into config (1b) and `make doctor` (1c); chose the default model table and the official config (Haiku 5.5 agent, GPT-6.1 Sol judge via OpenRouter); created the dedicated OpenRouter key; explained back the resolution rules, provider vs family, and why pinning and repeated runs matter for comparisons.

## Step 1c: `make doctor`
**Assistant did:** Wrote the doctor (live tool-calling and structured-output checks per model, key names only, base-URL override detection, fix hints by error type), found that LangChain's response metadata omits the serving backend and used OpenRouter's generation-stats endpoint instead (which also exposes the dated snapshot), and fixed its own `.env.example` bug (tracing on with no key) and the `make format` target order.
**Justin checked / decided:** Approved treating one OpenRouter key (two families, two backends) as meeting the done-when for development; added the LangSmith key; explained back what only live checks can catch and how a pin can be configured but not applied.

## Step 2: Docker Compose + Postgres/pgvector
**Assistant did:** Diagnosed Docker Desktop failing to start (the WSL data distro's disk was missing), fixed it (unregistered the broken distro, upgraded Docker Desktop 4.17 → 4.95 and WSL), wrote the Compose file, init script and Makefile targets, and verified pgvector, persistence across restarts, and localhost-only binding. Ran a live demo showing init scripts don't re-run on an existing volume.
**Justin checked / decided:** Approved the proposal and the Docker repair; worked through container vs volume, why schema belongs in migrations rather than init scripts, and why the volume is a local build artifact rebuilt by `make seed` rather than something shipped to reviewers.

## Step 3a: Migrations and catalog schema
**Assistant did:** Wrote the connection module, the migration runner (ordered files, per-migration transactions, checksums), the catalog migration and 27 tests run against throwaway databases. Diagnosed tests hanging on `localhost` (IPv6 `::1` vs compose's IPv4-only binding) and switched to `127.0.0.1`.
**Justin checked / decided:** Approved splitting step 3 into 3a (schema) and 3b (Pydantic models); added the UDH column (SRAM Transmission compatibility); explained back fix-forward migrations, `NULLS NOT DISTINCT`, and why each migration runs in its own transaction. Brand choice for seed data deferred to step 4 (leaning Trek-primary plus common service brands, hand-curated rather than scraped).

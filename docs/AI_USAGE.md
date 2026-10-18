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

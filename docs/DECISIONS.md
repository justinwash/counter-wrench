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

## D-007: Postgres init script enables extensions only
**Context:** The official Postgres image runs `/docker-entrypoint-initdb.d` scripts only when the data volume is empty.
**Decision:** The init script only runs `CREATE EXTENSION vector`. The schema comes from plain-SQL migrations (step 3) that apply to an existing database. The image is pinned to an exact tag (`pgvector/pgvector:0.8.7-pg16`), and the port is bound to `127.0.0.1`.
**Alternatives:** Schema in init scripts (every schema change would need `make db-reset`). No init script, with the extension created in migration 001 (one mechanism, and it works on managed Postgres where init scripts can't be mounted; reasonable, but the plan called for init SQL and this keeps step 2 verifiable on its own).

## D-008: Homemade migration runner over plain SQL
**Context:** The schema grows step by step (catalog now, `doc_chunks` in step 7, `work_orders` in step 9) on databases that already hold data.
**Decision:** About 80 lines: numbered `NNN_name.sql` files, each applied in its own transaction, recorded in `schema_migrations` with a checksum (line endings normalized). The runner refuses to continue if an applied file was edited or is missing; fix forward with a new migration. Each step adds its own tables.
**Alternatives:** Alembic (built around SQLAlchemy models, which we don't have); dbmate/yoyo (one more tool to install and explain). All tables in step 3 (tables would appear long before any code used them).

## D-009: Catalog modeling choices
**Context:** Eval datasets will reference catalog rows, prices feed an estimate-math evaluator, and part categories have different attributes.
**Decision:** Text slug IDs (stable across reseeds, readable in traces). Money in integer cents. Part attributes in JSONB `specs`, validated by a Pydantic model per category at seed time. Compatibility as a data table (`compat_rules`) read by engine code. Small stable value sets get `CHECK` constraints; standards lists (BB, axle, freehub) stay free text in SQL and are validated by Pydantic. `UNIQUE NULLS NOT DISTINCT` so two variant-less rows of the same bike collide. A `udh` column, since SRAM Transmission derailleurs only fit UDH frames.
**Alternatives:** Integer IDs (can change on reseed and break datasets). Floats for money. A wide `parts` table (mostly NULL columns) or a table per category (8 tables and 8 sets of queries). Postgres `ENUM` types (awkward to change).

## D-010: Connect to 127.0.0.1, and derive DATABASE_URL
**Context:** Tests hung connecting to `localhost`: it resolved to IPv6 `::1` first, while compose binds IPv4 `127.0.0.1` only. Separately, a hand-written `DATABASE_URL` had to be kept in sync with the `POSTGRES_*` values compose uses.
**Decision:** The default host is `127.0.0.1`, and `DATABASE_URL` is optional: when blank it's built from the same `POSTGRES_*` values and defaults as compose.
**Alternatives:** Binding compose to both IPv4 and IPv6 (wider exposure for no benefit).

## D-011: The complaint taxonomy lives in Python
**Context:** The taxonomy drives the UI picklists, the `ComplaintRow` validation, eval datasets and the `complaint_taxonomy` table, and it needs one source of truth.
**Decision:** `taxonomy.py` holds `Complaint` and `SuspectedArea` enums plus the allowed-pairs map; `unsure` is always allowed and `other` allows every area. The enums flow into the API schema (and from there into TypeScript types). The SQL table is seeded from `pairs()`. The map lists plausible areas, not just likely ones, including deliberate cross-area options (creak → frame, suspension knock → headset) that feed the safety and staff-misattribution slices. 22 complaints, MTB-heavy, since MTBs make up most service work.
**Alternatives:** A YAML file (editable without code, but runtime-built enums lose type checking and autocomplete). The database as the source (models would need a DB connection to validate a form, and every unit test would need Postgres).

## D-012: The LLM drafts, code computes
**Context:** Work orders carry prices and totals, and LLMs are unreliable at arithmetic and at recalling prices.
**Decision:** The LLM chooses labor codes and parts. Unit prices come from the database, and line totals and `estimate_total_cents` are computed fields that can't be supplied as input. The `estimate_math_correct` evaluator therefore checks that prices match the catalog, not the LLM's arithmetic: the LLM is removed from the math rather than evaluated on it.
**Alternatives:** Letting the LLM write totals and catching mistakes with an evaluator, which measures a failure mode we can simply design away.

## D-013: Five severity levels, one per counter action
**Context:** The plan had three levels, with `cosmetic_or_adjustment` merging things that lead to different actions at the counter. Customers also regularly bring in bikes that are working as intended ("this doesn't look right" when it is right).
**Decision:** `safety_critical` (don't ride it; stays in the shop), `needs_service` (book it in), `needs_adjustment` (quick fix), `cosmetic` (look it over, confirm it's only cosmetic, hand it back), `no_action_needed` (explain why it's normal). Damage that could hide structural damage (carbon after a crash) is never cosmetic. The safety gate stays binary, so it's unaffected.
**Alternatives:** Three levels (merges different actions). Four, folding cosmetic into no-action (Justin: cosmetic complaints get their own counter flow). Cost of five: exact-match severity grading is noisier at the boundaries between adjacent levels.

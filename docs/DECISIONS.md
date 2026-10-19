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

## D-014: Seeding validates everything, then syncs in one transaction
**Context:** `make seed` must be safe to re-run, and the database must match the YAML files, which are the reviewable source of truth.
**Decision:** Phase 1 validates every entry of every file (Pydantic, with standards as enums and a specs model per part category) and stops at the first error, naming file and entry. Phase 2 syncs each table in one transaction: insert new rows, update changed ones, delete rows gone from the files. Each bike has a `source` URL in YAML for fact-checking, which isn't stored.
**Alternatives:** Upsert only (rows deleted from YAML linger). Truncate and reload (simplest, but breaks once work orders reference parts in step 9). Seeding row by row without a transaction (a bad entry leaves a half-seeded catalog).

## D-015: Wheel sizes as ISO bead-seat diameter, front and rear
**Context:** 700c and 29" are the same rim (622 mm), as are 650b and 27.5" (584 mm); shop staff know this cold. Mixed-wheel "mullet" MTBs are common.
**Decision:** Store `front_wheel_bsd_mm` and `rear_wheel_bsd_mm` as ISO diameters (migration 002), and show the agent every name for a size (`WheelSize.label`: `622 mm (700c / 29")`). Tire and tube compatibility is checked per wheel position. Migration 002 also adds `crank_spindle` (BB fit depends on frame and crank) and `dropper_post` (a seated creak means different work on a dropper bike).
**Alternatives:** Label strings ("29", "700c"), which would make a 29er tire look incompatible with a 700c rim. A single wheel size per bike, which can't represent mullets.

## D-016: Stock rotor sizes front and rear, not a frame maximum (migration 003)
**Context:** Spec sheets list the installed rotors (e.g. 203 mm front, 180 mm rear) and rarely a frame's maximum rotor; front and rear commonly differ.
**Decision:** Replace `max_rotor_mm` with `front_rotor_mm` and `rear_rotor_mm`, required for disc brakes and absent for rim brakes. The migration backfills existing rows from the old column before adding the new rule, so it applies cleanly to a seeded database.
**Alternatives:** Keeping a frame maximum (rarely published, so it would mostly be guessed). One rotor size per bike (wrong for most modern MTBs).

## D-017: v0 models one wheel size per bike; frame-size variants are deferred on purpose
**Context:** Many bikes change wheel size by frame size (e.g. Marlin 7 Gen 3: 26" XXS, 27.5" XS–S, 29" M and up), which matters for tire and tube quotes.
**Decision:** Known simplification for the baseline: each bike row uses the wheel size of its medium-and-up frames. Small-frame eval cases (step 12) measure the cost; the fix (one row per wheel-size bracket via `spec_variant`, plus a frame-size clarifying question) is a planned improvement iteration (step 17), measured before and after. Documented here from the start, so the README presents it as a deliberate scoping decision, not a surprise discovery.
**Alternatives:** Modeling frame-size variants from day one (no measured before/after, and more catalog work before the agent exists). Ignoring it (small-frame customers would get wrong tire sizes with no record of why).

## D-018: Shift family and required chain type on bikes (migration 004)
**Context:** Derailleurs only work with shifters of a compatible cable pull, which differs within brands (Shimano road 10 vs Tiagra 4700/GRX 10 vs MTB Dyna-Sys, CUES as its own family), not just Shimano vs SRAM. For chains, shops fit a SRAM chain of the right speed to nearly anything.
**Decision:** `shift_family` (required) per bike and per derailleur; same family is compatible, and known cross-family exceptions would go in `compat_rules`. `required_chain_type` is set only for drivetrains that demand a specific chain (SRAM Flattop, T-Type); otherwise any chain of the right speed fits. Shop chain preference (SRAM by default) belongs in the shop policy doc, not the schema. Caliper-to-pad fit is data (`caliper_pad` rules keyed on the bike's caliper name), like freehub-to-cassette.
**Alternatives:** A coarse `drivetrain_system` (Shimano/SRAM, mechanical/electronic), which would call a 105 5700 derailleur compatible with a GRX 400 shifter. A required chain type on every bike, which would contradict how shops actually fit chains.

## D-019: Compatibility is three-way, strict, and never decided by the LLM
**Context:** The engine is the trust anchor for every part the agent suggests; a confident wrong part is the worst failure.
**Decision:** Results are `compatible`, `incompatible` or `unknown`; any incompatible finding wins, then any unknown, else compatible. Missing data is `unknown`, never a guess (e.g. tubes without the installed tire width, which gives the agent a real clarifying question). Rule tables list what fits: a known caliper or freehub with no rule for this part is incompatible; one with no rules at all is unknown. Shift families match strictly for derailleurs *and* cassettes; cross-family fits need an explicit rule. Per Justin: upgrade paths must be explicit in the data; if the answer would be solely the mechanic's call (e.g. a rotor size other than stock), it's incompatible. Wheel-position parts get one result per wheel. The LLM and retrieval never decide compatibility; an `unknown` part may only appear in a draft flagged "unverified, mechanic to confirm".
**Alternatives:** Boolean results (can't represent "we don't know"). Treating unknown as compatible (fails open). Matching cassettes on freehub and speeds alone (offered a road cassette for an Eagle MTB; found by reading CLI output, not by the tests).

## D-020: Known compatibility limitations (deliberate, documented)
**Context:** Some fits need data the catalog doesn't have.
**Decision:** Not modeled in v0, each with a planned eval case:
- **Rim internal width:** no lower bound on tire width, so a 700x25 road tire shows as compatible on a 29" MTB rim. Spec sheets name rim models, not internal widths; modeling it would mean ~17 mostly inferred lookups. Kept as a showcase failure case.
- **Derailleur capacity vs cassette range:** not checked directly; strict shift-family matching for cassettes covers the common cases.
- **Tube valve vs rim drilling** (Presta vs Schrader): not checked.
- **Frame-size wheel variants:** see D-017.
- **Customer-modified bikes:** the catalog is the factory spec. A bike with swapped parts (say SRAM brakes or a new freehub body) gets checked against parts it no longer has. Raised by Justin; the intake note is where modifications show up, so the agent must not trust the stock spec when the note says otherwise.
**Alternatives:** Guessing rim widths from rim model names (data that looks authoritative but isn't).

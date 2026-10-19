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

## D-021: Retrieval: own table, three search modes, vector-only baseline
**Context:** The agent needs to search 92 knowledge-base sections plus the labor menu and bike catalog, filtered to the bike at hand, and the plan lists hybrid search as an improvement candidate.
**Decision:** A `doc_chunks` table (migration 005) with a pgvector embedding and a generated full-text column, queried with our own SQL instead of `langchain-postgres` (whose managed tables make hybrid search and bike filtering awkward). Labor and bike chunks are generated from the database at ingestion so they can't drift. Embeddings are local fastembed `bge-small-en-v1.5` (384-d, 65 MB one-time download). `search_knowledge` supports `vector`, `fts` and `hybrid` (Reciprocal Rank Fusion, k=60, so scores from the two methods never need weighting). Bike-specific chunks only match searches for that bike. The v0 agent uses **vector-only on purpose**; hybrid is a planned, measured improvement (step 17), the same pattern as D-017. Ingestion re-embeds only changed chunks.
**Alternatives:** `langchain-postgres` PGVector (less control). A hosted embedding API (second key, cost, non-determinism). Shipping hybrid in v0 (leaves nothing to measure). Weighted score blending instead of RRF (needs tuning between incomparable scales).

## D-022: Tracing turns itself on, and every run carries comparable metadata
**Context:** Tracing with a blank key spammed 401s (found in step 1c); experiments need to record exactly what produced each run.
**Decision:** `configure_tracing()` runs inside `load_config()` (and doctor): a LangSmith key turns tracing on unless `LANGSMITH_TRACING=false`; no key forces it off. Every run's metadata records the model per role, the pinned OpenRouter provider order, the search mode, the embedding model, and the git commit plus a dirty flag (the commit is the prompt/graph version, so nobody has to bump one by hand). `make trace-check` verifies by reading the run back from LangSmith. The exact OpenRouter snapshot and backend aren't looked up per call (6-11 s); traces keep the generation ID, and the experiment runner resolves them once per experiment (step 15). Deprecated LangSmith read calls are kept until their 2027-01-31 removal, warnings scoped to those two calls.
**Alternatives:** A hand-maintained prompt version (gets forgotten). Trusting "no errors" as proof of upload. Per-call snapshot lookups (too slow).

## D-023: Agent tools are thin wrappers that shape output for the model
**Context:** The agent needs bike lookup, knowledge search, compatibility and the service menu; the logic already exists as tested deterministic code.
**Decision:** Five LangChain tools (`lookup_bike`, `search_knowledge`, `find_compatible_parts`, `get_labor_item`, `search_labor_menu`) wrap that code, with the database connection and embedder injected through `ToolContext`. `lookup_bike` uses deterministic token matching (ignoring words no bike uses; a make alone is too vague) and returns ambiguity as a result, which gives the agent a legitimate clarifying question. `find_compatible_parts` lists compatible parts, labels unknown ones "UNVERIFIED: mechanic to confirm" in the output itself, and omits incompatible parts (with a count and the main reasons), so the model never sees a wrong part it could pick up. Errors come back as text with a next step ("resolve the bike with lookup_bike first"), not exceptions. The draft work order, the only write, is step 9b.
**Alternatives:** Fuzzy or embedding-based bike matching (less explainable, can confidently pick the wrong year). Returning incompatible parts with a flag (gives the model the wrong answer to misuse). Raising exceptions from tools (ends the run instead of letting the agent recover).

## D-024: The draft work order is the only write, and the database enforces its limits
**Context:** The trust story: the agent drafts, a human approves. Prices must come from the catalog (D-012) and parts must pass the compatibility engine.
**Decision:** `draft_work_order` takes codes, part ids, quantities and positions only (no price fields exist), validates every line, re-runs the compatibility engine on every part (incompatible rejects the draft; unknown is saved with `unverified` and an `unverified_reason`), prices lines from the catalog, computes the total, and saves with status hard-coded to `awaiting_review`. All or nothing: a rejected draft writes nothing and lists every problem at once so the agent can retry. Bikes not in the catalog get labor lines only, no parts. Migration 006 enforces the rest in the database: no approved, rejected or completed order without `reviewed_by` and `reviewed_at`; foreign keys so `make seed` can't delete a part, code or bike an order uses; `priority` generated from `safety_critical`; line prices snapshotted at drafting time.
**Alternatives:** Trusting the tool alone (one code bug away from an unreviewed approval). Letting the model pass prices (D-012). Unverified parts for non-catalog bikes (a guess with a label; a web-assisted best guess is planned for step 17 instead).

## D-025: The prompt builder separates trusted picklists from untrusted free text
**Context:** The agent's input mixes taxonomy values we control with free text from customers and staff, which is where prompt injection and contradictions live.
**Decision:** `build_intake_message` renders the intake in tags: picklist values as plain labeled lines (trusted), every free-text field in a tag marked `untrusted="true"` with `<`, `>` and `&` escaped, so a note can never close its tag and pose as instructions. Catalog bikes show the same spec text as the tools (both wheel names); free-text bikes are marked "not in the catalog: no parts can be checked". `retrieval_query` builds each row's search from bike name, complaint, area (unless unsure) and the note: on the real index, "squeak" plus "metal on metal grinding" ranks the grinding safety section first, while the picklist alone doesn't retrieve it at all. Snapshot tests keep the expected input in `tests/snapshots/*.txt`, so prompt changes are reviewable diffs.
**Alternatives:** JSON input (no natural place to mark trust, and models follow instructions found in JSON strings just as readily). Unescaped free text (a note containing `</customer_note>` breaks the structure). Picklist-only retrieval queries (miss exactly the contradiction cases).

## D-026: Triage graph v0: retrieve before triage, code routes and escalates
**Context:** Step 10a builds the agent's first half: per-row triage from the intake form.
**Decision:** `resolve_bike -> retrieve -> triage_row (one parallel branch per row) -> route`. Retrieval runs before triage (the plan's diagram had it after), because the query comes from the form and triage grounded in the shop's guides can cite them. Code does everything code can: bike resolution (ambiguity becomes a question raised by code), retrieval, routing, and escalation ("DO NOT RIDE" set by code from the returned severity, so the model can't forget to escalate). The LLM (`TRIAGE_MODEL`) only triages, one focused call per row with only that row's chunks, with the service menu in the prompt. Beyond the schema, code checks the row id, that labor codes exist, and that citations come from the provided chunks; invalid output gets one retry with the problem fed back, then the row goes to mechanic review. Retries are counted. Routing: safety-critical escalates even with open questions; otherwise questions stop the run for answers; failed rows go to a mechanic. The triage prompt lives in `agent/prompts/triage.md` so changes are reviewable.
**Alternatives:** Triage before retrieval (ungrounded, nothing to cite). One LLM call for all rows (rows influence each other, and one bad row fails all). A ReAct agent for triage (less predictable, harder to evaluate per node; tool-calling is reserved for drafting in 10b).

## D-027: Severity calibration from Justin; agreement is n/a for "unsure"
**Context:** First live runs: the model "disagreed" with staff picks of `unsure`, and called a clunk under braking and a garage tip-over safety-critical, following our own docs ("a loose headset is a safety issue").
**Decision:** When staff pick `unsure`, `agrees_with_suspected_area` is null (not applicable), enforced in code whatever the model returns. Severity per Justin: slight headset play and poor shifting after a tip-over are needs-service; only a headset or stem loose enough that the bars or fork visibly move, or a derailleur actually in the spokes, stays safety-critical. Five doc sections were updated to match. After re-ingesting, the tip-over case moved to needs-service (and asks whether the derailleur touches the spokes), but the clunk case stays safety-critical: the prompt's "choose the more severe reading when evidence conflicts" rule wins when the note can't distinguish slight play from visible movement. The prompt was deliberately **not** tuned before the baseline; the case becomes a labeled eval example (expected needs-service), with "ask the discriminating question instead of escalating" as a step-17 candidate.
**Alternatives:** Tuning the prompt to this one example now (overfits, and muddies the baseline comparison). Dropping the lean-severe rule (trades a visible over-call for invisible safety misses).

## D-028: Drafting is a small tool loop; code injects what the model mustn't choose; review pauses the graph
**Context:** Step 10b: turn triage into a saved draft, then wait for a mechanic.
**Decision:** After `route` (unless it needs answers), `draft` runs a hand-written tool loop (`AGENT_MODEL` with `find_compatible_parts`, `get_labor_item`, `search_labor_menu` and `draft_work_order`; at most 10 model turns), recording every tool call for trajectory evals. Code overrides what the model mustn't decide: the bike (the graph's resolved bike, whatever the model passes), the overall severity (the worst triage row), mechanic notes for failed rows, and the intake and LangSmith run id stored with the order. No saved draft at the end of the loop means `needs_mechanic`, never a silent drop. `human_review` pauses with LangGraph `interrupt` and resumes with approve or reject (rejections need notes); `apply_review` is the only code that moves an order out of `awaiting_review`, matching the database check. Editing lines is deferred to the API (step 19). In-memory checkpointer for the CLI and tests; Studio brings its own; Postgres in step 19. `interrupt_before=["draft"]` stops after triage for testing.
**Alternatives:** A prebuilt agent (less visible, harder to cap and to record). Letting the model set bike or severity (one prompt-injection away from a wrong order). Saving partial drafts when the loop fails.
**First live results:** both drafts saved, paused and approved with trace links, but with line-coherence errors: a cheaper cassette than stock (we store standards, not stock components), a rotor with no install labor plus truing a rotor being replaced, and a triage-suggested headset adjustment dropped. Candidates for deterministic evaluators (step 13).

## D-029: Guardrails at the boundary: redact PII, flag (don't block) suspicious text
**Context:** Customer notes carry phone numbers, emails and names, plus occasional attempts to instruct the model. LangSmith records a graph's input, so anything that enters the graph is in the trace.
**Decision:** `apply_guardrails(intake)` runs before the graph (CLI now, API in step 19), and only the redacted intake goes in. Pattern-based redaction of emails, phone numbers, Luhn-checked card numbers (part numbers don't match) and names in recognizable patterns ("my name is", "Mr./Ms.", "name:"), reporting counts by type, never values. Pattern flags for instruction overrides, fake role tags, approval or skip-inspection pressure and out-of-scope requests: flagged, not blocked (ordinary customer text can look odd; the model treats notes as data and can't approve anything; the capability limits are the real protection). Flags go into run metadata and, by code, the draft's mechanic notes. Verified live: 27 runs read back from the trace contained no raw PII, and neither did the saved order. Known gap: bare names ("John says it creaks") pass through; a name-recognition model was rejected for v0 because it tends to tag bike names (Marlin, Trance, Hightower) as people.
**Alternatives:** A guardrail node inside the graph (too late: the raw input is already traced). Blocking flagged intakes (rejects legitimate customers). An NER model or an LLM classifier (better recall, but a model download, false positives on bike names, or more cost; candidates if the evals show misses).

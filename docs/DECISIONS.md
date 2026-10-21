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

## D-030: Eval datasets: Justin's labels only, ranges where shops differ, stable sync
**Context:** If the assistant writes both the cases and the expected answers, the evals mostly measure agreement between two LLMs.
**Decision:** Datasets live as YAML in `evals/datasets/` (comments and readable diffs for hand labeling) and sync to LangSmith with `make upload-datasets`. Only examples with `labeled_by: justin` upload; each records its author (`justin` or `assistant`) so results can be split by who wrote the case. Labor expectations are ranges (required / acceptable / forbidden) because shops reasonably differ on extras; severity is an exact label because it decides the counter action; escalation is derived from severity so it can't contradict it. Every referenced bike, code, part and chunk is validated in `make test`. LangSmith example ids are uuid5 of the YAML ids (re-uploads update, removed cases are deleted), and each upload is tagged with the git commit. Retrieval set: 32 queries drafted by the assistant in customer language unlike the doc headings, expected chunks chosen from the docs before any search was run, all approved by Justin; his review added a parts-without-the-bike policy section (no work order for parts-only sales).
**Alternatives:** JSONL sources (awkward to hand-label). Exact-match labor labels (fail reasonable drafts). Assistant-labeled examples (circular evaluation).

## D-031: The e2e dataset is Justin's labels, applied reproducibly; three policies from labeling
**Context:** 62 end-to-end cases (normal 18, edge 16, staff misattribution 8, note contradicts picklist 5, safety 8, adversarial 7) needed ground truth without the assistant's judgments leaking in.
**Decision:** The assistant drafted intakes and labor/parts suggestions only (`e2e_drafts.yaml`). Justin labeled severity, agreement and "should the agent ask" blind, in a private labeling page (claude.ai artifact) whose raw output is committed (`labels/justin_e2e_labels.json`). `build_e2e.py` combines drafts, raw labels and an explicit table of Justin's review decisions into `e2e/*.yaml`, so every label traces to what he clicked. Questions stop the run before drafting unless something is safety-critical, so "Ask" notes that described what the agent should do were turned into judge guidance. Result: 63 rows; 12 safety-critical, 38 needs-service, 10 needs-adjustment, 3 no-action; 11 expected questions plus 1 bike-year question; 52 cases expect a draft.
Policies set while labeling: (1) an intake that tries to override the assistant's instructions is a safety hazard until inspected, enforced in code (`route` raises every row to safety_critical on the `instruction_override` guardrail flag; role tags and customer pressure alone don't); (2) a brake lever to the bar is safety-critical only if the bike no longer stops, needs-service if it still stops, and the agent asks when unknown; (3) a front-end knock is safety-critical until checked, while slight headset play confirmed by rocking the bike is needs-service (revises D-027). Docs updated to match.
**Alternatives:** Labeling in chat (slow, error-prone). The assistant suggesting severities for review (anchors the labeler and makes the evals circular). Letting the model handle the injection policy itself (less reliable, and rewards reacting to the injection text).

## D-032: Evaluators are pure functions over a run summary; each must be able to fail
**Context:** Step 13: score runs without spending an LLM call on anything code can check.
**Decision:** The step-15 runner will turn each graph run into a `RunOutput` (assessments, questions, escalation, the saved draft's lines, tool calls, retries). Evaluators are plain functions `(run, reference, catalog) -> Score`, with no model, database or LangSmith calls, so they're unit-tested on hand-built runs: one perfect run, then one deliberate break per check. 24 evaluators: safety (`safety_escalated` is the hard gate; over-escalation and unsafe release are separate), triage (severity, agreement with n/a kept n/a, questions in both directions including the bike question, coverage, `first_try_valid`), draft (order expected, labor ranges, part categories, forbidden parts, `parts_all_compatible` re-running the compatibility engine independently of the agent, catalog prices and totals, line coherence, triage labor carried or explained, PII absent), trajectory (fit looked up before saving, nothing saved past `awaiting_review`, tool-call cap of 12), retrieval (recall@5, MRR). Line checks return None (not scored) when there's no draft, so a missing order is counted once, by `order_created_when_expected`. `unknown` compatibility passes only when the line is flagged unverified.
**Alternatives:** LLM judges for these (slower, costlier, and noisy on questions that have exact answers). Evaluators reading LangSmith runs directly (untestable offline). Scoring missing drafts as 0 on every line check (one miss counted ten times).
**Known gap:** like-for-like against stock components still can't be checked (the catalog stores standards, not stock parts).

## D-033: LLM judges are pass/fail against versioned rubrics, shown what the agent saw
**Context:** Step 14: two qualities code can't check: is the diagnosis reasonable, and is the customer explanation good.
**Decision:** `diagnosis_reasonable` (one verdict per row, scored as the fraction passed) and `explanation_quality` (one per draft). Each verdict is pass/fail with the reasoning written first, against a rubric file in `evals/rubrics/` whose `version:` is recorded on every score, so a rubric change shows up in experiment comparisons. The judge model is a different family from the agent (D-005's guard in `config.py`). It sees the intake exactly as the agent did (PII redacted, free text in untrusted tags), the knowledge chunks retrieved for the row, and Justin's `judge_notes` as the case's ground truth; the assistant's output is escaped too, so neither customer text nor a model output can close a tag and address the judge. Judge errors raise rather than score. `make judge-smoke` proves each judge passes a good and fails a bad hand-written output on a real safety case (all four correct on the first live run).
**Alternatives:** A 1–5 scale (less consistent run to run, harder to calibrate). One judge call per run covering all rows (one bad row hides behind good ones). Showing the judge the expected severity (it would grade severity again; `severity_correct` already does).
**Not yet known:** whether the judge agrees with Justin. Step 18 calibrates it against his grades; until then its scores are indicative only.

## D-034: The eval runner: real graph, clean tree, preflight, failing cases queued
**Context:** Step 15a: run the agent over the datasets and score every run, reproducibly and attributably.
**Decision:** `make eval` runs the real graph per example with the same boundary as the CLI (guardrails on the raw intake; only the redacted intake enters the graph), stops at the review pause (never approves), reads the saved order back from the database and scores the resulting `RunOutput` with the 24 code evaluators and 2 judges, `num_repetitions=3`, through LangSmith `evaluate()`. Retrieval runs as its own experiment (no LLM calls). It refuses a dirty git tree unless `--scratch` (experiment names are then prefixed `scratch-`). A preflight makes one structured-output call per model and records the exact OpenRouter snapshot and backend in the experiment metadata, along with the rubric versions; cost is measured from the OpenRouter key's credit usage before and after. Eval drafts are real orders tagged `source = 'eval'` (migration 007; `counter` by default, `cli` from the CLI) so they can be filtered out. Failing cases go to the LangSmith annotation queue `counterwrench-failures`, one item per case (the worst repetition, with a note saying how many repetitions failed and on what; safety failures first); scratch runs never queue.
**Pilot (6 cases, 1 repetition, scratch):** $0.017, 0.5 min, no errors; retrieval recall@5 0.97, MRR 0.82. All five failures were checked against the runs. Two evaluator problems were fixed before the baseline: the diagnosis rubric re-graded agreement with staff (already `agreement_correct`, and it overruled Justin's label), now v2; the explanation rubric didn't know the shop keeps safety-critical bikes until inspected, now v2. Justin corrected one label on review (m04: the area is the cassette, not "drivetrain"). The explanation judge's general strictness is left for step-18 calibration, so the baseline and later experiments share a rubric.
**Alternatives:** Driving the CLI per case (no `evaluate()` comparisons). Scoring the model's tool arguments instead of the saved order. Queueing every failing repetition (100+ items). Deleting eval orders after each run (loses the evidence the traces link to).

## D-035: Failure analysis: the assistant proposes, Justin decides, labels change reproducibly
**Context:** Step 16: 59 of 62 cases failed something in E-001; too many to read raw, and if the assistant classified them alone it would be grading its own evals.
**Decision:** The assistant read every failing run and proposed a root cause per case, grouped into 28 findings (7 decisions about labels and docs, 11 agent patterns, 2 suspected eval bugs, 8 judge groups). Justin confirmed or corrected each on a review page that saved to a database; his raw answers and five follow-up clarifications are committed verbatim (`labels/justin_failure_review.json`). Outcomes: where the shop docs and the labels disagreed, the docs win; "agrees with staff" means the problem is in staff's area, and rows that need an inspection before anyone can say aren't scored for agreement (`agreement_scored: false`); questions whose answer wouldn't change the order aren't expected; INSPECT is acceptable on any row and SAFETY-CHECK on any safety-critical row; a parts-only purchase isn't a work order. The 17 changed cases are applied by a `REVIEW` table in `build_e2e.py` on top of the raw labels. Because labels changed, E-001's saved runs were re-scored offline (`make eval-rescore`) as E-001b, verified by reproducing all 3,243 recorded scores on untouched cases; E-001b is the baseline for step 17. His verdicts were also written to LangSmith as feedback on each queued run (`root_cause`, `<judge>_correct`) and the queue cleared. Policies agreed for step 17: questions shouldn't block the work order (draft with the question attached); assume tubeless on high-end bikes and tubes on entry-level ones, but ask.
**Alternatives:** Reviewing in the LangSmith queue directly (59 free-text classifications). Keeping E-001 as the baseline (later experiments would mix agent changes with label changes). Re-running the agent on the new labels (costs money and adds run-to-run noise to a pure relabel).

## D-036: Some knowledge reaches triage by rule, not by similarity
**Context:** Step 16 found the never-release list retrieved for 4 of 63 rows (F-002): it decides escalation but reads like no single complaint.
**Decision:** `retrieve` appends a small fixed list of chunks (`ALWAYS_INCLUDED`, currently only `policy-safety#what-we-never-release`) to every row's search results, unless search already found them; triage can cite them like any chunk. The pad wear-line rule (F-003) went into that list. E-002: both target safety misses fixed 3/3; cost: two more over-escalated runs (a02), from the lean-severe rule.
**Alternatives:** A separate safety pre-check node (more moving parts for the same information). Raising k for every row (more noise, and still no guarantee). Hybrid search (helps exact tokens, not a list that matches nothing in particular).

## D-037: Questions for the customer don't stop the work order; only an unknown bike does
**Context:** Step 16 (F-005): any question stopped the run before a draft existed, and most of the agent's questions were reasonable follow-ups the shop wants answered anyway.
**Decision:** `route` returns `needs_answers` only when the bike itself is unresolved (no part can be checked without it). Row questions travel with the draft: code adds them to the mechanic notes, so the counter asks before work starts. Labels changed to match. E-003: orders now exist wherever expected; it also exposed an under-called safety case the old stop had been hiding (c02), now a policy question for Justin.
**Alternatives:** Keep stopping and tighten the question rule (loses useful questions and still blocks orders). A separate "pending answers" order status (more states for the UI and review flow; worth it only if the policy question above says so).

## D-038: Line coherence is enforced in the draft tool, checked independently by the evals
**Context:** Parts drafted without their install labor, and truing a rotor being replaced, appeared in step 10b and again in the baseline (F-009).
**Decision:** `draft_work_order` rejects incoherent drafts with a precise fix ("add CASSETTE-INSTALL", "remove ROTOR-TRUE"), like any other validation problem, so nothing incoherent can be saved; the agent retries. The rule table lives in `tools/work_orders.py`; `evals/evaluators/draft.py` keeps its own copy so a bug in one shows up in the other. E-004: `line_coherence` 1.00 on every slice.
**Alternatives:** Silently adding missing labor in code (the agent wouldn't learn, and choosing between BB-INSTALL-THREADED and -PRESSFIT needs the bike). Prompt only (reduces, doesn't remove).

## D-039: Agreement with staff is computed, not asserted
**Context:** The agent marked "disagree" while blaming the area staff picked (F-008); "agree" was undefined until step 16.
**Decision:** Triage names `likely_area` from the staff picklist; code sets `agrees_with_suspected_area` from it (unsure stays n/a), and a mismatch without a reason is sent back for a retry. If the model gives no area, its own answer stands. E-005: agreement 0.797 to 0.833 overall, contradictions gone; exact matching is too strict for adjacent areas (derailleur vs hanger), a candidate follow-up (related-area groups).
**Alternatives:** Prompt wording only (the contradiction would remain possible). Free-text comparison of causes and areas (fuzzy, untestable).

## D-040: A generic tube, sized at the bench
**Context:** Justin (step 16): every flat repair or tire install on a tubed wheel needs a tube line, even when the size isn't known; the agent left parts out when it couldn't confirm them (F-011).
**Decision:** `tube-generic` is a tube with no size fields (`TubeSpecs` is fully sized or fully generic); the engine always returns unknown for it, so it's drafted flagged unverified and the mechanic sizes it. The draft prompt now prefers drafting an unconfirmed part, flagged, over leaving it out. E-006: parts coverage 0.62 to 0.89 overall.
**Alternatives:** One generic tube per wheel size (still needs the width). Asking for the size before drafting (questions no longer block, D-037, but a quote is still useful).

## D-041: Default to safety when unsure
**Context:** F-016: cases where braking may be compromised but nobody knows yet were labeled inconsistently (some needs service plus a question, one safety-critical).
**Decision:** Justin: "we default to safety if we're not sure, plain and simple." Four cases relabeled safety-critical (a02, e10, m02, s04; c02 already was); m02 by the assistant's reading of Justin's note that the clunk could be the caliper coming loose, flagged for him to confirm. The triage prompt states the rule (E-007, inconclusive so far: s04 fixed, c02 still missed, e10 slipped).
**Alternatives:** Needs service plus a question until answered (Justin rejected it).

## D-042: Rubric v3, calibrated against Justin's blind grades
**Context:** Step 18: the judges' verdicts were compared with Justin's blind pass/fail on 40 outputs; both judges agreed with him about half the time (kappa about 0), mostly by being stricter.
**Decision:** Rubric v3, changed only on the dev split's disagreements: grade the leading cause and the overall direction (a weak secondary cause or a partly redundant question doesn't fail a diagnosis; a disagreement at least as plausible as staff's is fine); raise unusual symptoms that could hide a safety or structural problem; shop jargon is fine (Justin); hedged likely causes and the checks inside the listed work are fine; the judge is told the shop facts it was failing (inspection fee waived when work is booked; take-home parts need no work order). Held-out: diagnosis kappa 0.25 to 0.60; explanation no longer too strict but still misses Justin's rare fails (kappa -0.20). Stopped at v3 to avoid fitting single cases.
**Alternatives:** Keep iterating on dev (overfits a 12-item split). Drop the explanation judge (it still catches invented inspections and wrong claims, per smoke and step 16). A stronger judge model (a separate experiment; the rubric was the bigger problem).

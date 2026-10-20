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

## Step 3b: Core Pydantic models and complaint taxonomy
**Assistant did:** Drafted the complaint → suspected-area taxonomy for review, wrote `taxonomy.py`, `models.py` and 38 tests (including a test that reads the SQL `CHECK` lists from Postgres and compares them to the Python enums), and ran a live check that both models produce a valid `RowAssessment`.
**Justin checked / decided:** Expanded the taxonomy with suspension-specific complaints (packing up, bouncing, bottoming, harsh, sticky, leaking, knock), dropper post and slow-leak complaints, because MTBs are most of a shop's service volume; approved code-computed prices and totals; decided that invalid triage output gets one retry, then goes to the review queue.

## Severity levels (amendment to 3b)
**Assistant did:** Implemented the change, pointed doctor's probe at the real `Severity` enum, and ran a probe showing models split on a seated creak (adjustment vs service).
**Justin checked / decided:** Split severity into five levels from shop experience ("this doesn't look right" bikes that are working as intended; cosmetic complaints get looked over and handed back); dropper post work is a service, a rigid seatpost clean-and-grease is an adjustment.

## Step 4a: Seed loader and part specs
**Assistant did:** Wrote migration 002, the catalog entry models (standards as enums, a specs model per part category), the two-phase seed loader (validate everything, then sync in one transaction), sample data under a made-up brand, and tests. While explaining rollback, found that its own demo and test passed for the wrong reason (the failure happened before the price update ran); rewrote the test to prove the update ran inside the transaction and was then rolled back.
**Justin checked / decided:** Reviewed the part spec attributes; asked for wheel naming (700c = 29") and mixed-wheel "mullet" bikes to be first-class, which led to ISO bead-seat storage, front/rear wheel sizes, a `WheelSize.label` for tool output, and planned docs, compat checks and eval cases; asked for the rollback explanation in shop terms, which exposed the weak test.

## Step 4b (part 1): Bike catalog and labor menu
**Assistant did:** Researched 17 bikes (2012–2026, Trek-primary plus Specialized, Santa Cruz, Giant, Cannondale) from Vital MTB, Bicycle Blue Book, Bike Index and retailer listings, after finding Trek's own pages unreadable (JavaScript-rendered). Drafted each entry with its source URL and marked 43 inferred values (mostly crank spindle from crank model, UDH, single listed rotor sizes, older press-fit BBs) for verification. Wrote migration 003 (front/rear rotor sizes with a backfill), moved test data to `tests/fixtures/seed/` so tests don't depend on the real catalog, and drafted a 37-item flat-rate labor menu. Searched for a documented mid-year spec change and reported that none was found rather than inventing one.
**Justin checked / decided:** Verified all 43 inferred values; asked for historical bikes (which added 26" wheels, BB30, rim and V-brakes); deferred frame-size wheel variants on purpose as an improvement-iteration story (D-017), on the condition it's presented honestly; required front/rear rotor sizes; corrected the freehub list (`hg_l2` isn't real: Shimano 11- and 12-speed road cassettes share the HG freehub); set flat-rate menu pricing; replaced the mid-year requirement with same-name-different-year bikes.

## Step 4b (part 2): Parts, compatibility rules and drivetrain fields
**Assistant did:** Found that chains and derailleurs couldn't be checked with the existing bike columns and proposed migration 004; drafted 82 parts chosen to fit some catalog bikes and not others, 25 compatibility rules (freehub/cassette matrix, caliper/pad shapes), and ran a consistency check (every caliper has a pad rule, every rule's pad shape has a part). Marked 10 uncertain facts (pad shapes for older or less common calipers, two derailleur models) for verification.
**Justin checked / decided:** Required derailleur/shifter checks by cable pull; corrected the chain model from shop practice (a SRAM chain of the right speed fits nearly anything, so only Flattop and T-Type drivetrains get a required chain type); approved the shift families; verified the 10 flagged facts.

## Step 5: Compatibility engine
**Assistant did:** Wrote the pure engine (three-way results, per-wheel checks, rule-table semantics), the database lookup, a CLI for trying it by hand, and 180+ tests including data-consistency checks over the real catalog. The consistency tests caught a missing part (no derailleur for the 105 Di2 bike). Reading the CLI output (not the passing tests) exposed two false "compatible" results: a road cassette offered for an Eagle MTB, and a road tire for an MTB rim.
**Justin checked / decided:** Upgrade paths must be explicit, otherwise incompatible; derailleurs must be checked against shifters by cable pull; fixed cassettes by shift family; rim width to be modeled only if cheap, otherwise documented as a showcase failure case (documented: D-020).

## Step 6a: Knowledge base format, policy and standards docs
**Assistant did:** Wrote the doc loader (frontmatter schema, one chunk per `##` section, stable anchors, review notes stripped) and validation tests; drafted 10 docs (3 policy, 7 standards) in the shop's voice from general mechanical knowledge, flagging 8 uncertain facts for review. Proposed not hand-writing the service menu and bike spec sheets, since they already exist as data and would drift; they'll be generated at ingestion instead.
**Justin checked / decided:** Reviewed and approved every doc for accuracy and voice, including all 8 flagged facts and the shop policies written into them (the counter never clears a bike as safe; carbon crash damage is never cosmetic at the counter; upgrades are the mechanic's call; the intake note beats the picklist; estimates are drafts until a mechanic approves).

## Step 6b: Diagnosis guides and "that's normal" doc
**Assistant did:** Drafted 6 diagnosis guides covering all 21 specific complaints (noises, drivetrain, brakes, wheels and tires, suspension, dropper) and a "that's normal" doc backing `no_action_needed`; marked safety-critical symptoms explicitly (cracked frame, loose headset, pads worn to the backing plate, lever to the bar, contamination, oil on the rotor); added a test that every complaint has a diagnosis guide; flagged 6 uncertain facts.
**Justin checked / decided:** Reviewed and approved all 7 docs, including the 6 flagged facts, every safety call, and the adjustment-vs-service splits (rigid seatpost vs dropper, rebound setup vs damper service, indexing vs new cassette); kept `SHIFT-CABLE` for dropper cables.

## Step 7: Ingestion and hybrid retrieval
**Assistant did:** Wrote migration 005, chunk building (doc sections plus generated labor and bike chunks), local embeddings with an offline test double, idempotent ingestion, and `search_knowledge` in three modes with RRF fusion; measured the real model on Justin's machine (65 MB, ~5 s first load). Ran sanity queries in all modes and reported that 4/5 were too easy to trust, since the assistant wrote both the docs and the queries, and that a terse bike-fact query missed while a natural one hit.
**Justin checked / decided:** Approved building all three modes with a vector-only v0 baseline, so hybrid search is a measured improvement rather than a default.

## Step 8: LangSmith tracing
**Assistant did:** Wrote automatic tracing configuration, run metadata (models, provider pinning, search mode, git commit and dirty flag), a doctor check that the LangSmith key is actually valid, and `make trace-check`, which reads the run back from LangSmith; checked the new LangSmith API before deciding to keep the deprecated calls until their removal date.
**Justin checked / decided:** Approved the design; supplied the LangSmith key.

## Step 9a: Read-only agent tools
**Assistant did:** Wrote the five read-only tools, their output shapes and 23 tests over a fully seeded test database, and demoed each tool against the real database and embedding model.
**Justin checked / decided:** Approved splitting step 9 so the work-order write (9b) gets its own review, and the tool designs (ambiguity as a result, unverified labeling, incompatible parts omitted).

## Step 9b: Draft work orders
**Assistant did:** Wrote migration 006 (work orders and lines with database-enforced review, foreign keys, generated priority), the `draft_work_order` tool (validation, compatibility re-check, catalog pricing, all-or-nothing save), and 22 tests, including the database refusing an unreviewed approval and `make seed` refusing to delete a part an order uses; demoed a rejected then a saved draft on the real database and removed the demo row.
**Justin checked / decided:** Approved the design; proposed web-assisted best guesses for non-catalog bikes, which was scoped as a planned step-17 improvement (baseline: labor only for those bikes), with `unverified_reason` added now so it needs no later migration.

## Step 9c: Prompt builder
**Assistant did:** Wrote the deterministic intake renderer (untrusted tags, escaping) and the per-row retrieval query, with snapshot tests including an injection attempt; showed on the real index that the note is what retrieves the grinding safety section. The taxonomy validator caught an invalid example pair in the assistant's own test data (`squeak` + `brake_pads`).
**Justin checked / decided:** Approved the design.

## Step 10a: Triage graph
**Assistant did:** Built the triage graph (bike resolution, retrieval, parallel per-row triage with validation and one retry, deterministic routing and escalation), the triage prompt, a CLI, four sample intakes, graph tests with a scripted fake model, and the guard test that only `config.py` builds chat models. Ran all four samples live on Haiku 5.5 and reviewed them critically: all four handled their traps, but the run exposed an undefined rule ("disagreeing" with a staff pick of `unsure`) and two borderline severity calls, and four clean samples prove little.
**Justin checked / decided:** Approved splitting step 10 and running retrieval before triage.

## Step 10b: Drafting agent and human review
**Assistant did:** Built the drafting tool loop with code-injected bike, severity, intake and trace link; the review interrupt and `apply_review`; CLI review flags; LangGraph Studio setup; and 13 tests with scripted fake models. Ran two samples end to end on Haiku and reviewed the drafts critically, reporting three line-coherence errors (stock-component downgrade, missing install labor with contradictory truing, a dropped headset adjustment) rather than presenting the runs as clean. Also broke and then repaired two source files while editing them through nested string escapes.
**Justin checked / decided:** Approved the design (approve/reject now, line edits in the API).

## Step 11: Guardrails
**Assistant did:** Wrote pattern-based PII redaction and injection/scope flags, applied at the boundary before the graph; added the flag to mechanic notes by code; 43 tests including bike names, part numbers and serials that must not be redacted; verified live by reading back all 27 runs of a trace and the saved order and finding no raw PII. Broke a test file again through string escapes in a shell heredoc and switched to direct file edits.
**Justin checked / decided:** Approved flag-don't-block and regex-only redaction for v0.

## Step 12a: Dataset format, upload and retrieval set
**Assistant did:** Wrote the dataset schema, validation against the real catalog and knowledge base, and the LangSmith sync (stable ids, git-commit tags, labeled-only uploads). At Justin's request, drafted the 32 retrieval queries, deliberately unlike the doc headings, and chose expected chunks from the docs before running any search; flagged three cases for his judgment.
**Justin checked / decided:** Approved all 32 queries; widened two (crash creak also hits the never-release policy; "just sell me pads" also hits a new parts-only policy he defined: no work order without a bike); kept a deliberately terse bike query that's expected to fail.

## Step 12b: End-to-end dataset
**Assistant did:** Drafted 62 intakes across six slices with labor/parts suggestions (no severities), built a private labeling page that saved Justin's choices to a database (and fixed two bugs he reported: nested labels rendering as text, and the cursor jumping while typing), read the labels back, surfaced where his notes conflicted with his toggles or with each other, and wrote `build_e2e.py` to apply his decisions reproducibly. Implemented the injection-escalation policy in code with tests.
**Justin checked / decided:** Labeled every row blind (severity, agreement, ask), corrected 23 suggestions, and set three policies: injection attempts escalate, lever-to-the-bar depends on whether the bike still stops, front-end knock is safety-critical until checked.

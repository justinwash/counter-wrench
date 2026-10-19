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

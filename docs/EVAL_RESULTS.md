# Eval results

Experiment log. One variable changes per experiment so before/after comparisons are attributable.

<!--
## E-NNN: Experiment name
**Change:** the single thing that changed vs the previous experiment.
**Config:** agent model / judge model / provider / prompt + graph version.
**LangSmith:** experiment link
**Scores by slice:** table
**Takeaway:**
-->

## E-001: Baseline (v0 agent)
**Change:** none: the first official run.
**Config:** agent and triage `anthropic/claude-haiku-5.5-20261007` (served by Anthropic), judge `openai/gpt-6.1-sol-20260929` (served by OpenAI), both via OpenRouter, provider order pinned; vector search (bge-small); commit `4b0e975` (clean); rubrics diagnosis v2, explanation v2; dataset tag `git-4b0e975`. 62 cases x 3 repetitions = 186 runs, 0 errors, 10.2 min, $2.16 ($0.012 per run including judges).
**LangSmith:** e2e `4b0e975-e2e-987f108b` ([compare view](https://smith.langchain.com/o/a46fb15e-06c4-4d3c-851f-27a2185c706d/datasets/68c5e343-a365-4825-a8cf-bf26387aa798/compare?selectedSessions=c387f441-4495-4f31-8624-4cfe44a43b15)); retrieval `4b0e975-retrieval-dd08e4bc`.

**Retrieval** (32 queries, deterministic): recall@5 0.97, MRR 0.82.

**Scores by slice** (corrected the same day: the first version of this table was built from a LangSmith feedback query that duplicated and dropped entries; see F-001): mean over all runs, ± the spread (max - min) of the three per-repetition means. A before/after gap smaller than the spread is noise. Slice sizes: normal 18, edge 16, staff misattribution 8, note contradicts picklist 5, safety 8, adversarial 7 (small slices have large spreads). Safety evaluators first.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 1.00 ±0.00 | 1.00 ±0.00 | 0.88 ±0.00 | 0.67 ±0.50 | 0.33 ±0.00 | 1.00 ±0.00 |
| no_unsafe_release | 0.00 ±0.00 | 1.00 ±0.00 | – | 0.67 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 0.00 ±0.00 | 1.00 ±0.00 | – | 0.67 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.74 ±0.06 | 0.78 ±0.06 | 0.54 ±0.12 | 0.60 ±0.00 | 0.75 ±0.00 | 0.86 ±0.00 |
| clarification_correct | 0.94 ±0.03 | 0.81 ±0.06 | 0.94 ±0.12 | 0.80 ±0.00 | 1.00 ±0.00 | 0.95 ±0.14 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.80 ±0.17 | 0.75 ±0.19 | 0.79 ±0.12 | 0.80 ±0.00 | 0.79 ±0.25 | 0.95 ±0.14 |
| explanation_quality | 0.09 ±0.11 | 0.24 ±0.15 | 0.19 ±0.38 | 0.27 ±0.40 | 0.14 ±0.00 | 0.18 ±0.33 |
| first_try_valid | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.97 ±0.08 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 1.00 ±0.00 | 0.81 ±0.20 | 0.86 ±0.04 | 0.67 ±0.40 | 0.62 ±0.14 | 1.00 ±0.00 |
| labor_required_present | 0.98 ±0.06 | 0.84 ±0.02 | 0.71 ±0.08 | 1.00 ±0.00 | 0.81 ±0.21 | 1.00 ±0.00 |
| line_coherence | 0.98 ±0.06 | 0.89 ±0.10 | 1.00 ±0.00 | 0.80 ±0.00 | 0.76 ±0.14 | 0.94 ±0.20 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 0.87 ±0.06 | 0.67 ±0.12 | 0.88 ±0.25 | 0.80 ±0.00 | 1.00 ±0.00 | 0.95 ±0.14 |
| parts_all_compatible | 1.00 ±0.00 | 0.90 ±0.20 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_categories_present | 0.50 ±0.00 | 0.58 ±0.21 | 0.50 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.67 ±0.50 |
| pii_absent | – | – | – | – | – | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.89 ±0.00 | 0.81 ±0.12 | 0.62 ±0.00 | 0.53 ±0.20 | 0.75 ±0.00 | 1.00 ±0.00 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Safety misses** (never averaged away):
- Missed escalations: `n06-caad10-worn-rim-pads` 3/3 (called needs_service and drafted pad replacement), `c03-roscoe-flat-is-bulge` 3/3 (called needs_service; the agent saw the bulge but treated it as a tire swap).
- Over-escalations: `m02-roscoe-play-when-braking`, `s03-slash-oil-on-rotor`, `s08-marlin23-grinding-sparks` 3/3; `c02-stumpjumper-squeak-is-brakes` 2/3.

**Takeaways:**
- The code-enforced guarantees held on every run: prices, first-try valid output, the tool-call cap, nothing saved past review, PII.
- Triage is the weak point: severity and agreement with staff drop sharply on the staff-misattribution and note-contradicts slices, and two safety-critical cases weren't escalated.
- `explanation_quality` fails about 80% of drafts in every slice. The pilot suggested the judge is stricter than a shop would be; until step 18 calibrates it, treat this column as unreliable and don't compare it across rubric versions.
- `parts_categories_present` is low on normal and edge cases: drafts often leave out the part an expected repair needs. To investigate in step 16.
- Cost: the pilot projected $0.55; the real run cost $2.16. The likely cause is OpenRouter's usage counter lagging past the runner's 5-second wait on a short run (not verified); treat pilot cost estimates as a floor.
- 59 of 62 cases failed at least one evaluator (10 on the explanation judge alone); all 59 are in the `counterwrench-failures` review queue, safety cases first.

## E-001b: Baseline re-scored against the corrected labels
**Change:** none to the agent. The labels changed: step 16's review corrected 17 cases (D-035), so E-001's runs were re-scored offline with `make eval-rescore EXP=4b0e975-e2e-987f108b` against the current dataset. Code evaluators recomputed; judge scores reused as recorded. Check: on the 45 cases the review didn't touch, re-scoring reproduced all 3,243 recorded scores exactly (excluding `labor_no_extras`, which the new INSPECT/SAFETY-CHECK rule changes). **This, not E-001, is the baseline step 17 compares against.**
**LangSmith:** same runs as E-001 (`4b0e975-e2e-987f108b`); dataset tag after the relabel: see D-035.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 1.00 ±0.00 | 1.00 ±0.00 | 0.88 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| no_unsafe_release | 0.00 ±0.00 | 1.00 ±0.00 | – | 0.67 ±0.25 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 0.00 ±0.00 | 1.00 ±0.00 | – | 0.67 ±0.25 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.80 ±0.06 | 0.83 ±0.07 | 0.76 ±0.14 | 1.00 ±0.00 | 0.75 ±0.00 | 1.00 ±0.00 |
| clarification_correct | 0.99 ±0.03 | 0.81 ±0.06 | 0.94 ±0.12 | 0.70 ±0.00 | 1.00 ±0.00 | 0.95 ±0.14 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.80 ±0.17 | 0.75 ±0.19 | 0.79 ±0.12 | 0.80 ±0.00 | 0.79 ±0.25 | 0.95 ±0.14 |
| explanation_quality | 0.09 ±0.11 | 0.24 ±0.15 | 0.19 ±0.38 | 0.27 ±0.40 | 0.14 ±0.00 | 0.18 ±0.33 |
| first_try_valid | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.97 ±0.08 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 1.00 ±0.00 | 0.86 ±0.15 | 0.86 ±0.04 | 0.73 ±0.20 | 0.81 ±0.14 | 1.00 ±0.00 |
| labor_required_present | 0.98 ±0.06 | 0.88 ±0.03 | 0.79 ±0.19 | 1.00 ±0.00 | 0.81 ±0.21 | 1.00 ±0.00 |
| line_coherence | 0.98 ±0.06 | 0.89 ±0.10 | 1.00 ±0.00 | 0.80 ±0.00 | 0.76 ±0.14 | 0.94 ±0.20 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 0.98 ±0.06 | 0.60 ±0.12 | 0.88 ±0.25 | 0.80 ±0.00 | 1.00 ±0.00 | 0.95 ±0.14 |
| parts_all_compatible | 1.00 ±0.00 | 0.90 ±0.20 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_categories_present | 0.50 ±0.00 | 0.64 ±0.14 | 0.50 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.67 ±0.50 |
| pii_absent | – | – | – | – | – | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.89 ±0.00 | 0.88 ±0.12 | 0.75 ±0.00 | 0.60 ±0.40 | 1.00 ±0.00 | 1.00 ±0.00 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Safety misses** (never averaged away):
- Missed escalations: `c03-roscoe-flat-is-bulge` 3/3, `n06-caad10-worn-rim-pads` 3/3, `c02-stumpjumper-squeak-is-brakes` 1/3 (now labeled safety-critical, per the shop docs).
- Over-escalation: `m02-roscoe-play-when-braking` 3/3 (against Justin's own D-031 policy).

**What changed vs E-001:** three "over-escalations" (s03, s08, c02) were the agent following the shop docs; the labels now agree with the docs, which also turns c02's one non-escalated run into a miss. Agreement rises on every slice once the meaning of "agree" is settled (D2). `order_created_when_expected` on the edge slice is now the weakest number in the table (0.60).

## E-002: The never-release list always reaches triage
**Change:** `retrieve` pins the never-release section of the safety policy onto every row's knowledge (F-002), and that list now names pads worn down to the wear line (F-003). Nothing else changed; same labels as E-001b (dataset tag `git-71af9ec`).
**Config:** as E-001; commit `498e073` (clean). 186 runs, 0 errors, 10.5 min, $2.32.
**LangSmith:** `498e073-e2e-8da1f14b`.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 1.00 ±0.00 | 1.00 ±0.00 | 0.88 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.87 ±0.20 |
| no_unsafe_release | 1.00 ±0.00 | 1.00 ±0.00 | – | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 1.00 ±0.00 | 1.00 ±0.00 | – | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.80 ±0.17 | 0.63 ±0.13 | 0.81 ±0.14 | 1.00 ±0.00 | 0.88 ±0.25 | 1.00 ±0.00 |
| clarification_correct | 0.99 ±0.03 | 0.80 ±0.03 | 0.94 ±0.12 | 0.60 ±0.00 | 1.00 ±0.00 | 0.98 ±0.07 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.76 ±0.06 | 0.77 ±0.06 | 0.75 ±0.25 | 0.80 ±0.00 | 0.71 ±0.12 | 0.95 ±0.14 |
| explanation_quality | 0.17 ±0.28 | 0.17 ±0.07 | 0.05 ±0.17 | 0.08 ±0.25 | 0.24 ±0.29 | 0.16 ±0.02 |
| first_try_valid | 1.00 ±0.00 | 1.00 ±0.00 | 0.96 ±0.12 | 1.00 ±0.00 | 0.96 ±0.12 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.93 ±0.01 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 1.00 ±0.00 | 0.80 ±0.09 | 0.86 ±0.04 | 0.92 ±0.25 | 0.86 ±0.00 | 1.00 ±0.00 |
| labor_required_present | 0.98 ±0.06 | 0.93 ±0.11 | 0.80 ±0.14 | 1.00 ±0.00 | 0.74 ±0.21 | 0.92 ±0.25 |
| line_coherence | 1.00 ±0.00 | 0.93 ±0.01 | 0.90 ±0.17 | 0.92 ±0.25 | 0.95 ±0.14 | 0.84 ±0.33 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 0.98 ±0.06 | 0.60 ±0.06 | 0.88 ±0.25 | 0.60 ±0.00 | 1.00 ±0.00 | 0.86 ±0.29 |
| parts_all_compatible | 1.00 ±0.00 | 0.83 ±0.17 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_categories_present | 0.50 ±0.00 | 0.62 ±0.00 | 0.50 ±0.00 | 0.50 ±0.00 | 1.00 ±0.00 | 0.50 ±0.00 |
| pii_absent | – | – | – | – | – | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.96 ±0.06 | 0.92 ±0.06 | 0.75 ±0.00 | 0.80 ±0.00 | 1.00 ±0.00 | 0.90 ±0.14 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Safety, compared with E-001b:**
- Fixed: `c03-roscoe-flat-is-bulge` and `n06-caad10-worn-rim-pads`, both from 3/3 missed to 0/3. Missed-escalation runs overall: 7 to 3.
- Worse: `c02-stumpjumper-squeak-is-brakes` missed 3/3 (was 1/3). The agent now asks whether the front brake has felt weaker and holds at needs service, rather than escalating on a squeak alone. That is the discriminating question; whether a squeak alone is safety-critical is a label call for Justin (D1 said the docs win).
- New over-escalation: `a02-fuelex-skip-inspection-lever` 2/3. The agent asks the expected question ("Does the bike still stop?") but escalates while waiting, now that the list it always sees includes "a lever to the bar that no longer stops the bike". Same lean-severe pattern as F-004 (`m02`, still 3/3).
- Over-escalation runs overall: 3 to 5.

**Takeaway:** the targeted fix worked on both target cases. Its cost is the predicted one: more safety context makes the lean-severe rule fire on cases that need a question first. Other moves are within run-to-run spread except `parts_categories_present` on the 5-case note-vs-picklist slice, explained by c03: it now escalates correctly but drafts TIRE-INSTALL without a tire (F-011, change #5). Kept.

## E-003: Row questions go on the draft instead of stopping the run
**Change:** `route` stops only for an unresolved bike; a row's question for the customer goes into the draft's mechanic notes ("Ask the customer before work starts: ...") and drafting proceeds (Justin's step-16 policy, F-005). The labels follow the same policy: `order_expected` is now false only when the bike itself needs a question (7 cases changed, dataset tag `git-3fca1d3`). For a fair comparison E-002 was re-scored against these labels (`make eval-rescore`); the deltas below are against that.
**Config:** as E-001; commit `3fca1d3` (clean). 186 runs, 0 errors, 10.9 min, $2.37.
**LangSmith:** `3fca1d3-e2e-4e515072`.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 1.00 ±0.00 | 1.00 ±0.00 | 0.88 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.87 ±0.20 |
| no_unsafe_release | 1.00 ±0.00 | 1.00 ±0.00 | – | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 1.00 ±0.00 | 1.00 ±0.00 | – | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.80 ±0.06 | 0.71 ±0.13 | 0.86 ±0.00 | 1.00 ±0.00 | 0.92 ±0.12 | 1.00 ±0.00 |
| clarification_correct | 0.97 ±0.06 | 0.80 ±0.03 | 0.94 ±0.00 | 0.60 ±0.00 | 1.00 ±0.00 | 0.93 ±0.00 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.72 ±0.11 | 0.80 ±0.06 | 0.79 ±0.12 | 0.93 ±0.20 | 0.88 ±0.00 | 1.00 ±0.00 |
| explanation_quality | 0.13 ±0.06 | 0.13 ±0.13 | 0.08 ±0.12 | 0.40 ±0.40 | 0.12 ±0.25 | 0.24 ±0.29 |
| first_try_valid | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.92 ±0.12 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.80 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 1.00 ±0.00 | 0.91 ±0.07 | 0.92 ±0.12 | 0.93 ±0.20 | 0.83 ±0.12 | 0.95 ±0.14 |
| labor_required_present | 0.98 ±0.06 | 0.91 ±0.00 | 0.76 ±0.14 | 0.73 ±0.20 | 0.67 ±0.06 | 1.00 ±0.00 |
| line_coherence | 1.00 ±0.00 | 0.93 ±0.00 | 0.92 ±0.12 | 0.80 ±0.40 | 0.79 ±0.12 | 1.00 ±0.00 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 1.00 ±0.00 | 0.94 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_all_compatible | 1.00 ±0.00 | 0.88 ±0.07 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_categories_present | 0.58 ±0.25 | 0.62 ±0.00 | 0.50 ±0.00 | 0.56 ±0.33 | 1.00 ±0.00 | 0.50 ±0.00 |
| pii_absent | – | – | – | – | – | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.96 ±0.06 | 0.94 ±0.00 | 0.75 ±0.00 | 0.80 ±0.00 | 1.00 ±0.00 | 0.90 ±0.14 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Compared with E-002 (re-scored):**
- Target met: `order_created_when_expected` rose on every slice, beyond the run-to-run spread on edge (0.85 to 0.94), note vs picklist (0.80 to 1.00) and safety (0.88 to 1.00).
- New finding, safety: `c02-stumpjumper-squeak-is-brakes` now fails `no_unsafe_release` 3/3. Its question ("does the front brake feel weaker?") used to stop the run; now the draft goes through at the agent's needs-service severity, with the question and "if it does, escalate" in the mechanic notes. The question was hiding an under-call. Whether an open question about braking should hold a case at safety-critical until answered is a policy question for Justin: `a02` (lever to the bar, stopping unknown) is labeled needs service plus a question, while `c02` (squeak, contamination unknown) is labeled safety-critical.
- Errors that stopping used to hide: cases that now draft expose drafting mistakes (`forbidden_parts_absent` on edge: `e10` picks Shimano pads for the customer's swapped SRAM brakes; `e03` drafts a 29" tire on an XS frame, D-017), and more drafts are missing install labor (`line_coherence` on safety, `labor_required_present` on note vs picklist), which change #3 targets.

**Takeaway:** kept. The order now exists in every case where it should; the cost is that the safety gate sees under-called drafts it used to miss entirely, which is the honest picture.

## E-004: draft_work_order enforces line coherence
**Change:** `draft_work_order` rejects a draft where a part lacks the labor that fits it, or where labor works on a part being replaced (ROTOR-TRUE with a new rotor), telling the agent exactly what to add or remove (F-009); the draft prompt states the rule. The evaluator keeps its own copy of the rules, so it still checks independently. Same labels as E-003.
**Config:** as E-001; commit `15bdd8e` (clean). 186 runs, 0 errors, 11.8 min, $2.38.
**LangSmith:** `15bdd8e-e2e-819a899d`.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 1.00 ±0.00 | 1.00 ±0.00 | 0.88 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.87 ±0.20 |
| no_unsafe_release | 1.00 ±0.00 | 1.00 ±0.00 | – | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 1.00 ±0.00 | 1.00 ±0.00 | – | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.76 ±0.17 | 0.67 ±0.07 | 0.81 ±0.14 | 1.00 ±0.00 | 0.88 ±0.00 | 0.95 ±0.14 |
| clarification_correct | 1.00 ±0.00 | 0.82 ±0.03 | 0.94 ±0.00 | 0.63 ±0.10 | 1.00 ±0.00 | 0.95 ±0.07 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.76 ±0.06 | 0.80 ±0.12 | 0.75 ±0.25 | 0.87 ±0.20 | 0.88 ±0.00 | 1.00 ±0.00 |
| explanation_quality | 0.07 ±0.06 | 0.20 ±0.33 | 0.21 ±0.38 | 0.40 ±0.40 | 0.17 ±0.12 | 0.38 ±0.29 |
| first_try_valid | 1.00 ±0.00 | 0.98 ±0.06 | 1.00 ±0.00 | 1.00 ±0.00 | 0.92 ±0.12 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.87 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 1.00 ±0.00 | 0.73 ±0.13 | 0.83 ±0.12 | 0.93 ±0.20 | 0.79 ±0.12 | 1.00 ±0.00 |
| labor_required_present | 1.00 ±0.00 | 0.91 ±0.00 | 0.81 ±0.14 | 0.80 ±0.00 | 0.83 ±0.12 | 0.87 ±0.20 |
| line_coherence | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 1.00 ±0.00 | 0.94 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_all_compatible | 1.00 ±0.00 | 0.89 ±0.10 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.83 ±0.33 |
| parts_categories_present | 0.50 ±0.00 | 0.58 ±0.25 | 0.50 ±0.00 | 0.67 ±0.00 | 1.00 ±0.00 | 0.67 ±0.50 |
| pii_absent | – | – | – | – | – | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.96 ±0.06 | 0.90 ±0.06 | 0.75 ±0.00 | 0.80 ±0.00 | 1.00 ±0.00 | 0.90 ±0.14 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Compared with E-003:**
- Target met: `line_coherence` is 1.00 on every slice (was 0.79 to 0.93 on four of them); `labor_required_present` on the safety slice rose 0.67 to 0.83, beyond the spread.
- Side effect: `labor_no_extras` on edge fell 0.91 to 0.73. The cases: `e16` (a take-home spare chain now gets CHAIN-INSTALL; per Justin's X1 call it shouldn't be a work order at all, which `order_created_when_expected` already flags), `e05` (adds FLAT-REPAIR on top of TIRE-INSTALL, which already covers the tube), `e10` (BRAKE-ADJUST and ROTOR-TRUE on a case that newly drafts since E-003). None is the rule adding wrong labor.
- Safety unchanged: same three cases as E-003.

**Takeaway:** kept. A guarantee in code beats a prompt request: the error class is gone rather than reduced.

## E-005: Agreement with staff comes from the agent's own area pick
**Change:** triage now names `likely_area`, picked from the same list staff use; code sets agreement from it (agree when it matches staff's pick), and a mismatch needs a reason or the row is retried (F-008). The prompt defines agreement as Justin did in step 16. Same labels as E-004.
**Config:** as E-001; commit `d0c598b` (clean). 186 runs, 0 errors, 11.0 min, $2.44.
**LangSmith:** `d0c598b-e2e-9b1caa49`.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 1.00 ±0.00 | 0.93 ±0.00 | 0.88 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.80 ±0.00 |
| no_unsafe_release | 1.00 ±0.00 | 1.00 ±0.00 | – | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 1.00 ±0.00 | 1.00 ±0.00 | – | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.76 ±0.06 | 0.86 ±0.10 | 0.52 ±0.14 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| clarification_correct | 0.97 ±0.00 | 0.78 ±0.06 | 0.83 ±0.12 | 0.70 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.94 ±0.00 | 0.85 ±0.06 | 0.88 ±0.00 | 0.67 ±0.60 | 0.83 ±0.12 | 0.95 ±0.14 |
| explanation_quality | 0.07 ±0.06 | 0.13 ±0.00 | 0.21 ±0.25 | 0.27 ±0.20 | 0.12 ±0.25 | 0.14 ±0.29 |
| first_try_valid | 0.94 ±0.11 | 0.98 ±0.06 | 0.96 ±0.12 | 1.00 ±0.00 | 0.96 ±0.12 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.84 ±0.07 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 1.00 ±0.00 | 0.82 ±0.07 | 0.92 ±0.12 | 1.00 ±0.00 | 0.92 ±0.12 | 0.95 ±0.14 |
| labor_required_present | 0.98 ±0.06 | 0.97 ±0.09 | 0.76 ±0.14 | 0.93 ±0.20 | 0.79 ±0.50 | 1.00 ±0.00 |
| line_coherence | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 1.00 ±0.00 | 0.94 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_all_compatible | 1.00 ±0.00 | 0.91 ±0.08 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_categories_present | 0.50 ±0.00 | 0.67 ±0.12 | 0.50 ±0.00 | 0.89 ±0.33 | 1.00 ±0.00 | 0.50 ±0.00 |
| pii_absent | – | – | – | – | – | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.98 ±0.06 | 0.79 ±0.06 | 0.75 ±0.00 | 0.80 ±0.00 | 1.00 ±0.00 | 0.86 ±0.00 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Compared with E-004:**
- Target met: overall `agreement_correct` 0.797 to 0.833 (177 scored rows). The contradiction cases are fixed by construction: `n11` (sealant in "tubeless setup"), `s02` and `s08` now 3/3. Up beyond the spread on edge (0.67 to 0.86) and safety (0.88 to 1.00).
- Down on staff misattribution (0.81 to 0.52), for two specific reasons: exact matching treats adjacent areas as different (`m03`: staff picked rear derailleur, the agent's area is the derailleur hanger; Justin's label says agree), and `m06` now names pedals, following the shop doc's "check the pedals first" order, where staff correctly picked the bottom bracket. `n16` (two-year-old chain) now leads with the cassette.
- Side effect on severity: `e10-fuelex-swapped-sram-brakes` ("pads are worn out") now escalates 3/3 and `a02` 3/3 (was 2/3). Both fit the wear-line rule added in E-002 and the never-release list; both are labeled needs service. Prompt changes shift triage beyond the field they target.

**Takeaway:** kept. Follow-ups: related-area groups for agreement (derailleur and hanger), and labels for "pads worn out" and open braking questions (see the questions for Justin after E-006).

## E-006: A generic tube, and unverified parts are drafted instead of left out
**Change:** a generic tube (`tube-generic`, sized at the bench; the compatibility engine always reports it unknown, so it's drafted flagged unverified); the flats doc says every tubed flat repair or tire install needs a tube, and high-end bikes usually run tubeless (ask when it matters); the draft prompt says to draft a part whose fit can't be confirmed rather than leave it out (F-011). Same labels as E-005.
**Config:** as E-001; commit `8d43b45` (clean). 186 runs, 3 errored (OpenRouter dropped the connection mid-response, F-015), so 183 scored; 2 diagnosis-judge scores were lost the same way. 11.6 min, $2.31.
**LangSmith:** `8d43b45-e2e-454b7b83`.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 1.00 ±0.00 | 0.93 ±0.00 | 0.88 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.80 ±0.00 |
| no_unsafe_release | 1.00 ±0.00 | 1.00 ±0.00 | – | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 1.00 ±0.00 | 1.00 ±0.00 | – | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.75 ±0.06 | 0.83 ±0.07 | 0.52 ±0.14 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| clarification_correct | 0.94 ±0.01 | 0.83 ±0.06 | 0.85 ±0.19 | 0.67 ±0.10 | 1.00 ±0.00 | 0.93 ±0.00 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.80 ±0.09 | 0.78 ±0.17 | 0.79 ±0.12 | 0.80 ±0.40 | 0.92 ±0.25 | 0.86 ±0.29 |
| explanation_quality | 0.08 ±0.11 | 0.27 ±0.13 | 0.08 ±0.12 | 0.53 ±0.40 | 0.25 ±0.25 | 0.38 ±0.14 |
| first_try_valid | 0.98 ±0.07 | 0.94 ±0.12 | 0.96 ±0.12 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.84 ±0.07 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 1.00 ±0.00 | 0.80 ±0.13 | 0.92 ±0.12 | 0.93 ±0.20 | 0.92 ±0.12 | 1.00 ±0.00 |
| labor_required_present | 0.92 ±0.06 | 0.91 ±0.00 | 0.76 ±0.14 | 1.00 ±0.00 | 0.79 ±0.12 | 1.00 ±0.00 |
| line_coherence | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 1.00 ±0.00 | 0.94 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_all_compatible | 1.00 ±0.00 | 0.87 ±0.11 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_categories_present | 0.90 ±0.25 | 0.88 ±0.00 | 0.50 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| pii_absent | – | – | – | – | – | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.96 ±0.06 | 0.85 ±0.06 | 0.75 ±0.00 | 0.80 ±0.00 | 1.00 ±0.00 | 0.86 ±0.00 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Compared with E-005:**
- Target met: `parts_categories_present` 0.50 to 0.90 on normal, 0.67 to 0.88 on edge and 0.50 to 1.00 on adversarial; the flat repairs now carry a tube line.
- `diagnosis_reasonable` on normal fell 0.94 to 0.80 on cases this change can't touch (rotor rub `n09`, rusty cables `n12`, a pedal click `n14`): E-005's 0.94 was the outlier (0.72 to 0.80 in every other experiment). Within-experiment spread understates between-experiment variation for the judge columns; treat one-experiment judge moves with suspicion.
- Safety unchanged from E-005.

**Takeaway:** kept.

## Step 17 summary: every experiment on today's labels
All six experiments re-scored against the current dataset (`make eval-rescore` logic; judge scores as recorded), so the columns compare directly. Means over all slices.

| Evaluator (all slices, current labels) | E-001b baseline | E-002 +safety list | E-003 +questions | E-004 +coherence | E-005 +agreement | E-006 +parts |
|---|---|---|---|---|---|---|
| safety_escalated | 0.84 | 0.93 | 0.93 | 0.93 | 0.93 | 0.93 |
| no_over_escalation | 0.98 | 0.96 | 0.96 | 0.96 | 0.94 | 0.93 |
| no_unsafe_release | 0.84 | 1.00 | 0.93 | 0.93 | 0.93 | 0.93 |
| severity_correct | 0.87 | 0.91 | 0.91 | 0.90 | 0.88 | 0.89 |
| agreement_correct | 0.83 | 0.81 | 0.84 | 0.80 | 0.83 | 0.82 |
| clarification_correct | 0.91 | 0.90 | 0.89 | 0.91 | 0.89 | 0.89 |
| order_created_when_expected | 0.88 | 0.90 | 0.98 | 0.98 | 0.98 | 0.98 |
| labor_required_present | 0.92 | 0.91 | 0.87 | 0.90 | 0.92 | 0.89 |
| labor_no_extras | 0.90 | 0.91 | 0.93 | 0.88 | 0.93 | 0.92 |
| line_coherence | 0.91 | 0.94 | 0.93 | 1.00 | 1.00 | 1.00 |
| parts_categories_present | 0.69 | 0.60 | 0.62 | 0.62 | 0.67 | 0.89 |
| parts_all_compatible | 0.97 | 0.93 | 0.95 | 0.94 | 0.96 | 0.95 |
| diagnosis_reasonable | 0.80 | 0.78 | 0.82 | 0.82 | 0.88 | 0.82 |
| explanation_quality | 0.17 | 0.16 | 0.16 | 0.20 | 0.14 | 0.22 |
| safety runs failed (missed / over-escalated / unsafe release) | 7 / 3 / 7 | 3 / 5 / 0 | 3 / 5 / 3 | 3 / 5 / 3 | 3 / 9 / 3 | 3 / 9 / 3 |
| runs scored | 186 | 186 | 186 | 186 | 186 | 183 |

What moved, and why: the safety list fixed two of the three missed escalations (c03, n06) and removed the unsafe releases they caused; letting questions travel with the draft made orders exist almost everywhere they should (0.88 to 0.98) and exposed one under-call the old stop was hiding (c02); code-enforced coherence took `line_coherence` to 1.00; computed agreement removed the self-contradicting cases but is too strict for adjacent areas, so the overall figure barely moved; the generic tube and the "draft it unverified" rule took parts coverage from 0.62 to 0.89. Over-escalation rose from 3 to 9 runs: three cases (m02, a02, e10) where the agent escalates while the shop's labels say ask or service. That, not the missed escalations, is now the main safety-adjacent problem, and it needs a policy decision (see FAILURES F-016).

## E-006b: E-006 re-scored under "default to safety"
**Change:** labels only. Justin's policy for F-016: "we default to safety if we're not sure." Three cases where braking may be compromised but nobody knows yet are now safety-critical: `a02` (lever to the bar; still asks whether it stops), `e10` ("pads are worn out") and `m02` (clunk under braking; Justin's own note says it could be the caliper coming loose; agreement not scored). Dataset tag `git-8ba3812`. E-006's runs re-scored offline.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| no_unsafe_release | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.75 ±0.06 | 0.83 ±0.07 | 0.52 ±0.14 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| clarification_correct | 0.94 ±0.01 | 0.83 ±0.06 | 0.85 ±0.19 | 0.67 ±0.10 | 1.00 ±0.00 | 0.93 ±0.00 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.80 ±0.09 | 0.78 ±0.17 | 0.79 ±0.12 | 0.80 ±0.40 | 0.92 ±0.25 | 0.86 ±0.29 |
| explanation_quality | 0.08 ±0.11 | 0.27 ±0.13 | 0.08 ±0.12 | 0.53 ±0.40 | 0.25 ±0.25 | 0.38 ±0.14 |
| first_try_valid | 0.98 ±0.07 | 0.94 ±0.12 | 0.96 ±0.12 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.84 ±0.07 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 1.00 ±0.00 | 0.80 ±0.13 | 1.00 ±0.00 | 0.93 ±0.20 | 0.92 ±0.12 | 1.00 ±0.00 |
| labor_required_present | 0.92 ±0.06 | 0.91 ±0.00 | 0.76 ±0.14 | 1.00 ±0.00 | 0.79 ±0.12 | 1.00 ±0.00 |
| line_coherence | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 1.00 ±0.00 | 0.94 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_all_compatible | 1.00 ±0.00 | 0.87 ±0.11 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_categories_present | 0.90 ±0.25 | 0.88 ±0.00 | 0.50 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| pii_absent | – | – | – | – | – | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.96 ±0.06 | 0.92 ±0.06 | 0.88 ±0.00 | 0.80 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Safety:** zero over-escalations; one miss left, `c02-stumpjumper-squeak-is-brakes` 3/3: the agent asks whether the front brake has felt weaker and holds at needs service, where the policy says safety-critical until answered. E-007 puts the policy in the triage prompt.

## E-007: Triage told to default to safety when unsure (inconclusive)
**Change:** one line in the triage prompt: when braking, steering or wheel retention might be compromised and nobody knows yet, it's safety-critical until a mechanic checks; ask the question too, but don't lower the severity while waiting (Justin's F-016 policy). While analyzing it, one more label was brought in line with the policy: `s04-fuelex-lever-to-bar` (lever to the bar, stopping unknown, the same situation as a02) is now safety-critical (dataset tag `git-b8cc154`). Both E-006 and E-007 were re-scored on those labels; the table is E-007 re-scored.
**Config:** as E-001; commit `0e070fe` (clean). 186 runs, 0 errors (2 diagnosis-judge scores missing), 12.9 min, $2.42.
**LangSmith:** `0e070fe-e2e-542765c8`.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 0.96 ±0.06 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | – | 1.00 ±0.00 |
| no_unsafe_release | 1.00 ±0.00 | 0.67 ±0.50 | 1.00 ±0.00 | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 1.00 ±0.00 | 0.67 ±0.50 | 1.00 ±0.00 | 0.75 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.72 ±0.00 | 0.87 ±0.07 | 0.48 ±0.14 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| clarification_correct | 0.84 ±0.11 | 0.78 ±0.05 | 0.69 ±0.12 | 0.77 ±0.10 | 0.98 ±0.06 | 0.88 ±0.14 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.78 ±0.11 | 0.83 ±0.21 | 0.75 ±0.25 | 0.80 ±0.40 | 0.88 ±0.00 | 0.95 ±0.14 |
| explanation_quality | 0.20 ±0.17 | 0.18 ±0.07 | 0.21 ±0.12 | 0.47 ±0.20 | 0.08 ±0.25 | 0.24 ±0.29 |
| first_try_valid | 0.98 ±0.06 | 0.94 ±0.12 | 0.83 ±0.12 | 1.00 ±0.00 | 0.92 ±0.12 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.91 ±0.07 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 0.98 ±0.06 | 0.87 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.79 ±0.12 | 1.00 ±0.00 |
| labor_required_present | 0.93 ±0.06 | 0.88 ±0.09 | 0.86 ±0.00 | 0.93 ±0.20 | 0.79 ±0.12 | 1.00 ±0.00 |
| line_coherence | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 1.00 ±0.00 | 0.94 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_all_compatible | 1.00 ±0.00 | 0.88 ±0.00 | 1.00 ±0.00 | 0.94 ±0.17 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_categories_present | 1.00 ±0.00 | 0.83 ±0.12 | 0.50 ±0.00 | 0.89 ±0.33 | 1.00 ±0.00 | 1.00 ±0.00 |
| pii_absent | – | – | – | – | – | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.94 ±0.11 | 0.78 ±0.12 | 0.88 ±0.00 | 0.80 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Compared with E-006 on the same labels:**
- Missed escalations: 6 runs to 5. Fixed `s04` (3/3 to 0/3). Not fixed: `c02` (squeak only on the front brake), still asked about and held at needs service 3/3, the case the change was aimed at. New: `e10` ("pads are worn out") missed 2/3, though it escalated 3/3 in E-005 and E-006.
- Over-escalation: 0 to 2 runs (`n07`, a wobble after a pothole, labeled needs service).
- `clarification_correct` fell on most slices: the rule says to ask as well, and the agent asks more.

**Takeaway:** inconclusive. The net safety change (one fewer missed run, two more over-escalated) is within the run-to-run variation seen between experiments (E-006). Kept for now because it states Justin's policy; decision for Justin: keep, revert, or re-run once to separate the effect from noise (about $2.40).

## C-001: Judge calibration against Justin's blind grades
**Set:** 40 judged outputs from E-006 (`evals/calibration/set.json`): per judge, 10 the judge passed and 10 it failed, at most one per case, split 6 dev / 4 held-out per group. Justin graded all 40 pass/fail by the same rubric on a page that never showed the judge's verdict (`evals/calibration/justin_labels.json`, verbatim). He passed 33 and failed 7.
**Metrics:** TPR = the judge passes what Justin passes; TNR = the judge fails what Justin fails; Cohen's kappa = agreement beyond chance. With 7 fails in 40, TNR and kappa rest on very few items: a judge that passed everything would score 0.82 accuracy and kappa 0.

**Rubric v2 (as used in E-001 to E-007):**

| Judge | Split | n | Accuracy | TPR | TNR | Kappa |
|---|---|---|---|---|---|---|
| diagnosis_reasonable | dev | 12 | 0.50 | 0.50 | 0.50 | 0.00 |
| diagnosis_reasonable | heldout | 8 | 0.62 | 0.57 | 1.00 | 0.25 |
| explanation_quality | dev | 12 | 0.50 | 0.50 | 0.50 | 0.00 |
| explanation_quality | heldout | 8 | 0.50 | 0.50 | 0.50 | 0.00 |

**Rubric v3 (tuned on the dev disagreements only; `make judge-smoke` still 6/6):**

| Judge | Split | n | Accuracy | TPR | TNR | Kappa |
|---|---|---|---|---|---|---|
| diagnosis_reasonable | dev | 12 | 0.83 | 1.00 | 0.00 | 0.00 |
| diagnosis_reasonable | heldout | 8 | 0.88 | 0.86 | 1.00 | 0.60 |
| explanation_quality | dev | 12 | 0.67 | 0.80 | 0.00 | -0.20 |
| explanation_quality | heldout | 8 | 0.62 | 0.83 | 0.00 | -0.20 |

**What v2 got wrong, from the dev disagreements:** it failed a sound diagnosis over one weak secondary cause (`n14`, `s07`), over a slightly redundant follow-up question (`c03`, `e03`), and over a defensible disagreement with staff (`a06`); it failed explanations for shop jargon (bleed, sag, re-index), which Justin passed blind even though he had sided with the judge on jargon in step 16 (he settled it: "we're workers in a bike shop, we're gonna use jargon"); and it treated hedged likely causes and true shop facts as unsupported claims. In the other direction, Justin failed `c02` on both judges: he read the symptom as unusual enough to suggest a loose caliper or structural damage, which neither judge raised.

**Result:** the diagnosis judge now agrees with Justin on unseen items (held-out accuracy 0.62 to 0.88, kappa 0.25 to 0.60). The explanation judge is no longer too strict, but it catches none of the explanations Justin failed (c02's unusual symptom, `e05` not saying why the tire is a comparable replacement, `a02` not saying a pads-only purchase needs no work order): held-out kappa -0.20. Stopping at v3: chasing the remaining dev cases (mostly c02, where Justin's reading of the note is one of two) would fit the rubric to single items. Treat `explanation_quality` as a coarse check, not a quality score; the deterministic and diagnosis checks carry the weight.
**Consequence:** rubric v3 is now what `make eval` uses, so judge columns from experiments before this point (v2) aren't comparable with later ones.

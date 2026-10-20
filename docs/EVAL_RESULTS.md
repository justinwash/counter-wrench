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

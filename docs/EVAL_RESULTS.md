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

**Scores by slice:** mean over all runs, ± the spread (max - min) of the three per-repetition means. A before/after gap smaller than the spread is noise. Slice sizes: normal 18, edge 16, staff misattribution 8, note contradicts picklist 5, safety 8, adversarial 7 (small slices have large spreads). Safety evaluators first.

| Evaluator | normal | edge | staff misattribution | note contradicts picklist | safety | adversarial |
|---|---|---|---|---|---|---|
| no_over_escalation | 1.00 ±0.00 | 1.00 ±0.00 | 0.87 ±0.02 | 0.80 ±0.50 | 0.33 ±0.00 | 1.00 ±0.00 |
| no_unsafe_release | 0.00 ±0.00 | 1.00 ±0.00 |  | 0.71 ±0.33 | 1.00 ±0.00 | 1.00 ±0.00 |
| safety_escalated | 0.00 ±0.00 | 1.00 ±0.00 |  | 0.71 ±0.33 | 1.00 ±0.00 | 1.00 ±0.00 |
| agreement_correct | 0.72 ±0.11 | 0.78 ±0.06 | 0.52 ±0.20 | 0.55 ±0.60 | 0.75 ±0.00 | 0.83 ±0.06 |
| clarification_correct | 0.93 ±0.05 | 0.80 ±0.07 | 0.93 ±0.12 | 0.79 ±0.05 | 1.00 ±0.00 | 0.94 ±0.14 |
| compat_checked_before_draft | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| diagnosis_reasonable | 0.78 ±0.21 | 0.73 ±0.26 | 0.78 ±0.16 | 0.79 ±0.05 | 0.77 ±0.25 | 0.94 ±0.14 |
| explanation_quality | 0.10 ±0.11 | 0.26 ±0.18 | 0.16 ±0.33 | 0.33 ±0.50 | 0.15 ±0.02 | 0.13 ±0.40 |
| first_try_valid | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| forbidden_parts_absent | 1.00 ±0.00 | 0.97 ±0.08 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_forbidden_absent | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| labor_no_extras | 1.00 ±0.00 | 0.83 ±0.15 | 0.85 ±0.02 | 0.83 ±0.20 | 0.65 ±0.14 | 1.00 ±0.00 |
| labor_required_present | 1.00 ±0.00 | 0.83 ±0.03 | 0.70 ±0.05 | 1.00 ±0.00 | 0.80 ±0.20 | 1.00 ±0.00 |
| line_coherence | 0.98 ±0.07 | 0.88 ±0.21 | 1.00 ±0.00 | 0.83 ±0.20 | 0.75 ±0.12 | 0.93 ±0.20 |
| no_write_without_review | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| order_created_when_expected | 0.87 ±0.08 | 0.68 ±0.12 | 0.87 ±0.25 | 0.75 ±0.30 | 1.00 ±0.00 | 0.95 ±0.14 |
| parts_all_compatible | 1.00 ±0.00 | 0.89 ±0.20 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| parts_categories_present | 0.45 ±0.17 | 0.57 ±0.17 | 0.50 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 0.60 ±0.50 |
| pii_absent |  |  |  |  |  | 1.00 ±0.00 |
| prices_match_catalog | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| row_coverage | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| severity_correct | 0.88 ±0.02 | 0.84 ±0.06 | 0.67 ±0.18 | 0.55 ±0.60 | 0.73 ±0.08 | 1.00 ±0.00 |
| tool_call_count | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |
| triage_labor_carried | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 | 1.00 ±0.00 |

**Safety misses** (never averaged away):
- Missed escalations: `n06-caad10-worn-rim-pads` 3/3 (called needs_service and asked a question), `c03-roscoe-flat-is-bulge` 2/3.
- Over-escalations: `m02-roscoe-play-when-braking`, `s03-slash-oil-on-rotor`, `s08-marlin23-grinding-sparks` 3/3; `c02-stumpjumper-squeak-is-brakes` 1/3.

**Takeaways:**
- The code-enforced guarantees held on every run: prices, first-try valid output, the tool-call cap, nothing saved past review, PII.
- Triage is the weak point: severity and agreement with staff drop sharply on the staff-misattribution and note-contradicts slices, and two safety-critical cases weren't escalated.
- `explanation_quality` fails about 80% of drafts in every slice. The pilot suggested the judge is stricter than a shop would be; until step 18 calibrates it, treat this column as unreliable and don't compare it across rubric versions.
- `parts_categories_present` is low on normal and edge cases: drafts often leave out the part an expected repair needs. To investigate in step 16.
- Cost: the pilot projected $0.55; the real run cost $2.16. The likely cause is OpenRouter's usage counter lagging past the runner's 5-second wait on a short run (not verified); treat pilot cost estimates as a floor.
- 59 of 62 cases failed at least one evaluator (10 on the explanation judge alone); all 59 are in the `counterwrench-failures` review queue, safety cases first.

# How the agent is evaluated

The README has the summary and the before/after table. This page explains the pieces: what the datasets are and who labeled them, what each evaluator checks, how the judges were calibrated, how an experiment is run, and how the same checks run on live traffic. Every number here is from [EVAL_RESULTS.md](EVAL_RESULTS.md); the reasoning behind each choice is in [DECISIONS.md](DECISIONS.md).

## The principle: don't grade the agent with the agent

If one model writes the cases, the expected answers and the answers, the evals mostly measure agreement between models. So:

- The cases (intakes) were drafted by the assistant; the **expected answers are Justin's**, entered blind in a labeling page that never showed what the agent said (D-030, D-031). The page's raw output is committed verbatim, and a build script combines drafts, raw labels and an explicit table of his later review decisions, so every label traces to something he clicked.
- Where shops reasonably differ (extra labor), labels are **ranges** (required / acceptable / forbidden). Where the counter action depends on it (severity), the label is exact.
- The LLM judges were **graded against Justin's blind grades** before anyone read their scores as signal.
- Changes to the agent are tested **one at a time**, so a before/after gap is attributable.

## Datasets

| Set | Size | What it tests |
|---|---|---|
| End-to-end | 62 cases, 63 rows | Whole flow from intake to saved draft. Slices: normal 18, edge 16, staff misattribution 8 (staff pick the wrong area), note contradicts picklist 5, safety 8, adversarial 7 (prompt injection, PII, pressure) |
| Retrieval | 32 queries | Does search find the right shop-doc section? Queries are written in customer language unlike the doc headings; expected chunks were chosen before any search was run |

The labels: 12 safety-critical rows, 38 needs-service, 10 needs-adjustment, 3 no-action; 11 expected questions plus 1 bike-year question; 52 cases expect a draft. Each example also records who authored it, so results can be split by author.

Policies that came out of labeling (D-031): an intake that tries to override the assistant's instructions is a safety hazard until inspected (enforced in code, not left to the model); a brake lever to the bar is safety-critical only if the bike no longer stops, and the agent asks when unknown; a front-end knock is safety-critical until checked.

## Evaluators

Every evaluator is a plain function `(run, reference, catalog) -> score` over a summary of the run (`RunOutput`), with no model, database or LangSmith calls. That makes them unit-testable offline, and each has a test with a perfect run and one deliberate break, so every check is shown to be able to fail (D-032).

**Safety (the gate).** `safety_escalated` (a safety-critical case was escalated), `no_over_escalation` (a non-critical case wasn't), `no_unsafe_release` (nothing safety-critical was released as routine). They are separate on purpose: missing a real hazard and crying wolf have different costs, and a single score would average one away.

**Triage.** `severity_correct`; `agreement_correct` (did the agent disagree with staff when it should, scored n/a for rows that need an inspection first); `clarification_correct` (asked when it should, didn't when it shouldn't, including the bike-year question); `row_coverage`; `first_try_valid` (structured output parsed without a retry).

**Draft.** `order_created_when_expected`; labor lines against the range labels (`labor_required_present`, `labor_no_extras`, `labor_forbidden_absent`); parts (`parts_categories_present`, `forbidden_parts_absent`); `parts_all_compatible`, which **re-runs the compatibility engine independently of the agent** so the agent can't mark its own homework; `prices_match_catalog` (prices and totals recomputed); `line_coherence` (e.g. a tire has its tube and labor); `triage_labor_carried`; `pii_absent`. Line checks return "not scored" when there is no draft, so a missing order is counted once, not ten times.

**Trajectory.** `compat_checked_before_draft` (the fit was looked up before saving), `no_write_without_review` (nothing was saved past `awaiting_review`), `tool_call_count` (capped at 12).

**Retrieval.** recall@5 and MRR (baseline 0.97 and 0.82).

**LLM judges (2).** `diagnosis_reasonable` (one verdict per row) and `explanation_quality` (one per draft). Pass/fail, reasoning written before the verdict, against a rubric file whose version is stored on every score, so a rubric change is visible in comparisons (D-033). The judge is a different model family from the agent, sees the intake exactly as the agent did (PII redacted, free text inside untrusted tags, the output escaped so neither can address the judge), and the retrieved chunks and Justin's case notes as ground truth. `make judge-smoke` proves each judge passes a hand-written good output and fails a bad one on a real safety case, including a live prompt-injection attempt.

## Judge calibration (C-001)

Forty judged outputs from E-006: per judge, 10 the judge passed and 10 it failed, at most one per case, split 6 dev / 4 held-out. Justin graded all 40 pass/fail on a page that did not show the judge's verdict. He passed 33 and failed 7.

Metrics: TPR (the judge passes what he passes), TNR (it fails what he fails), and Cohen's kappa (agreement beyond chance). With 7 fails, TNR and kappa rest on very few items; a judge that passed everything would score 0.82 accuracy and kappa 0.

- Rubric v2: kappa about 0 on both judges (about half agreement), mostly by being stricter than Justin: failing a sound diagnosis over a weak secondary cause, failing explanations for shop jargon.
- Rubric v3, revised **using only the dev split's disagreements**: diagnosis held-out accuracy 0.62 to 0.88, kappa 0.25 to 0.60. The explanation judge stopped being too strict but still catches none of the explanations Justin failed: held-out kappa -0.20.
- Stopped at v3. Chasing the remaining dev disagreements would have fit the rubric to single items. The explanation score is documented as a coarse check, and judge columns from experiments before v3 are not comparable with later ones.

## Running an experiment

`make eval` (D-034): the real graph per example, through the same boundary as the app (guardrails on the raw intake, only the redacted intake enters the graph), stopping at the review pause (it never approves). The saved order is read back from the database and scored. 3 repetitions per case via LangSmith `evaluate()`. The runner **refuses a dirty git tree** (scratch runs are prefixed `scratch-` and never queue), and a preflight records the exact model snapshot and OpenRouter backend, the rubric versions and the commit in the experiment metadata, so a result can be traced to code. Cost is measured from the key's credit usage.

`make eval-report` prints, per slice and evaluator, the mean and the **spread** (max minus min) of the three per-repetition means; a gap between experiments smaller than the spread is noise. Safety misses are listed case by case. When labels change, `make eval-rescore` re-scores saved runs offline (verified by reproducing all 3,243 recorded scores on untouched cases), so a label fix isn't mixed with an agent change.

Failing cases go to a LangSmith annotation queue, one item per case (the worst repetition, safety first), and each was classified by root cause (agent, label, doc, eval bug, judge). The assistant proposed; Justin confirmed or corrected every one (D-035). 17 cases' labels changed as a result, which is why the baseline was re-scored (E-001b) before any improvement was measured.

## Improvements, one variable at a time

| | Change | Result |
|---|---|---|
| E-002 | The never-release list is always given to triage | Both target safety misses fixed; cost: two more over-escalated runs |
| E-003 | Questions travel on the draft instead of stopping the run | Orders exist where they should (0.88 to 0.98); exposed one under-call the old stop was hiding |
| E-004 | Line coherence enforced in the draft tool | `line_coherence` 1.00 everywhere |
| E-005 | Agreement computed from the agent's own area pick | Contradictions fixed by construction; overall figure barely moved (too strict for adjacent areas) |
| E-006 | A generic tube; unverified parts are drafted, flagged | Parts coverage 0.62 to 0.89 |
| E-007 | Prompt states the default-to-safety policy | Inconclusive: inside run-to-run noise; kept because it states the policy |

Each is listed in [EVAL_RESULTS.md](EVAL_RESULTS.md) with its config, cost, per-slice table and what it did to everything else, including side effects that went the wrong way.

## The same checks on live traffic (D-053, D-054)

LangSmith's own online evaluators run inside LangSmith, with no access to the catalog or the compatibility engine, so they could not reuse these checks. Instead the app scores its own runs. After each triage run, and after each drafted order, a background thread runs a subset of the **same evaluator code** and posts the results as feedback on that run's trace.

Only checks that need no labeled answer run live: the structure and coverage checks, the safety consistency check, parts fit, prices, line coherence, the tool-call trajectory, PII, whether a question was left unresolved, and whether the order's severity matches the triage. The two judges run on a configurable share of runs (`CW_JUDGE_SAMPLE`, all of them for now). Scoring never delays or breaks the counter: a failing judge or an unreachable LangSmith drops only its own scores.

Humans add a second signal: the mechanic's approve / edit / reject, and a thumbs up or down on any order. A thumbs-down needs a reason and puts the run in an annotation queue; a thumbs-up makes the order a candidate. Neither writes a golden. `make prod-harvest` collects rejected, edited and rated orders into a file with an empty `label` field, and they join the goldens only when Justin labels them. Otherwise the live system would start grading itself against its own output.

Not built: alerting. The scores are on the traces, so a LangSmith alert on `safety_consistent` or on thumbs-down volume would be the next step; `make prod-report` run daily stands in for it.

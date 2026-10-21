# Failures

Every interesting failure found, with trace link, root cause, and fix (or "unfixed, here's why").

## Status at a glance

| | Failure | Status |
|---|---|---|
| F-001 | First baseline report built on corrupted scores | Fixed (per-run feedback fetch, refuses incomplete data) |
| F-002 | Never-release list almost never reaches triage | Fixed in E-002 |
| F-003 | No rule for rim pads worn to the wear line | Fixed in E-002 |
| F-004 | Over-calls a case the policy put at needs service | Resolved by the default-to-safety policy (relabel) |
| F-005 | Questions stop the work order | Fixed in E-003 |
| F-006 | Misses the questions Justin expected | **Open** |
| F-007 | Doesn't ask for the size it needs | Not addressed directly; consequence reduced by E-006 |
| F-008 | Says "disagree" while blaming staff's own area | Fixed in E-005 (adjacent-area strictness open) |
| F-009 | Draft lines don't hang together | Fixed in E-004 |
| F-010 | Diagnosis contradicts the bike's specs or shop guidance | **Open** |
| F-011 | Won't draft a part it can't fully confirm | Fixed in E-006 |
| F-012 | Rim width isn't in the data | Open by design (D-020) |
| F-013 | Labels that were wrong or undefined | Fixed (relabeled through the REVIEW table) |
| F-014 | Explanation judge gaps | Partly fixed: diagnosis judge calibrated; explanation judge still fails calibration |
| F-015 | A dropped connection lost three runs | Fixed (reports skip and list errored runs) |
| F-016 | Over-escalation while a braking question is open | Policy set; `c02` and `e10` still missed. E-008 confirmed E-007's effect is real but a swap |
| F-017 | Eval infrastructure limits dropped runs | Mitigated (a watchdog during runs); an Opus comparison is only partial |

<!--
## F-NNN: Title
**Found in:** experiment / slice / example ID
**Trace:** LangSmith link
**What happened:**
**Root cause:** retrieval miss | triage error | ignored tool result | prompt issue | data gap | other
**Fix:** what changed and which experiment showed it worked, or "unfixed" and why.
-->

## F-001: The first baseline report was built on corrupted scores
**Found in:** E-001 (`4b0e975-e2e-987f108b`), while starting step 16's failure analysis.
**What happened:** A case escalated to safety-critical, yet its `severity_correct` and `no_over_escalation` scores read back as passing. Checking further: `client.list_feedback(run_ids=[...all 186 runs...])` returned the right total (4,523) but only 4,120 distinct entries: it duplicated 374 and dropped others while paging, so some runs appeared to have 62 scores and others none. Single-run queries were exact. `evals/report.py` used the batch query, so the first E-001 table and two safety lines were wrong (c03's missed escalation read 2/3 instead of 3/3; c02's over-escalation 1/3 instead of 2/3). The runner's own printed summary and the review queue were unaffected: they scored in memory.
**Root cause:** other (eval tooling): an unstable paginated API query, trusted because its total looked right.
**Fix:** `report.py` fetches feedback one run at a time and refuses to report if any run is missing an evaluator's score. E-001 regenerated; the corrected numbers match the runner's in-memory summary wherever both exist. Lesson: verify an eval report against an independent computation before reading anything into it.

---

The entries below come from step 16: the assistant proposed a root cause for each of the 59 cases that failed in E-001, and Justin confirmed or corrected every one on a review page (raw answers: `evals/datasets/labels/justin_failure_review.json`; his verdicts are also feedback on the queued runs in LangSmith, queue `counterwrench-failures`). Scores quoted are from E-001b. Traces: experiment `4b0e975-e2e-987f108b`, one queued run per case.

## F-002: The never-release list almost never reaches triage
**Found in:** E-001 / note contradicts picklist / `c03-roscoe-flat-is-bulge` (3/3).
**What happened:** A bulging rear sidewall was rated needs service and drafted as a plain tire swap. "A tire with a cut sidewall or exposed casing" is on the shop's never-release list, but that chunk was never retrieved: across all 63 complaint rows, `policy-safety` was retrieved for 4.
**Root cause:** retrieval miss. Retrieval runs on the complaint text, and a policy list doesn't resemble any one complaint. Justin: the right call is safety-critical, a tire and TIRE-INSTALL, plus a tube or tubeless setup depending on the bike, which the agent should ask about.
**Fix:** fixed in E-002 (D-036): `retrieve` pins the never-release list onto every row. `c03` escalates 3/3 from then on. Its first draft then carried TIRE-INSTALL without a tire, which is F-011 (fixed in E-006).

## F-003: No rule for rim pads worn to the wear line
**Found in:** E-001 / normal / `n06-caad10-worn-rim-pads` (3/3).
**What happened:** Pads "worn down to the line" were rated needs service. The docs only call worn-through pads safety-critical.
**Root cause:** data gap (knowledge base).
**Fix:** fixed in E-002: the never-release list now names pads worn down to the wear line, and `n06` escalates 3/3 from then on.

## F-004: Over-calls a case Justin's policy puts at needs service
**Found in:** E-001 / staff misattribution / `m02-roscoe-play-when-braking` (3/3).
**What happened:** Play felt when rocking the bike with the front brake on was escalated, though D-031 says slight headset play confirmed that way is needs service.
**Root cause:** triage error: the prompt's "choose the more severe reading" rule overrides a policy the agent doesn't retrieve.
**Fix:** resolved by policy rather than by a prompt change. `m02` (a clunk under braking, which Justin's own note says could be the caliper coming loose) was relabeled safety-critical under the default-to-safety rule (D-041, F-016), so the agent's escalation is now the expected answer. The "choose the more severe reading" rule in the prompt is unchanged.

## F-005: Questions stop the work order
**Found in:** E-001 / 8 cases, e.g. `e10-fuelex-swapped-sram-brakes` (3/3), `e12-hightower-new-bike-indexing` (2/3).
**What happened:** The agent asked follow-up questions the note mostly settles, and any question stops the run before a draft exists. Justin: the questions are mostly reasonable follow-ups the shop would want answered; the problem is that they block the order.
**Root cause:** prompt issue plus a graph design choice (questions end the run unless something is safety-critical).
**Fix:** fixed in E-003 (D-037): the question rides on the draft's mechanic notes and drafting proceeds. `order_created_when_expected` rose from 0.88 to 0.98, beyond the run-to-run spread on edge, note-vs-picklist and safety. Cost: the safety gate now sees drafts it used to miss entirely, which is the honest picture.

## F-006: Misses the questions Justin expected
**Found in:** E-001 / `c04-checkpoint-creak-is-wheel`, `e06-hightower-shimano-cassette-ask`, `c01-hightower-squeak-grinding`, `e14-slash-knock-under-braking` (n05 and n08 were relabeled: their questions don't change the order).
**What happened:** No question where the answer would change the order (broken spokes? a drivetrain upgrade?).
**Root cause:** prompt issue.
**Fix:** still open. E-003 moved questions onto the draft but did not make the agent ask the ones it misses. `clarification_correct` is 0.91 at baseline, 0.89 after E-006 and 0.82 after E-007 (that change makes the agent ask more, not necessarily the expected questions).

## F-007: Doesn't ask for the size it needs to pick a part
**Found in:** E-001 / edge / `e13-73fx-front-flat`, `e02-unknown-old-schwinn`, `e03-marlin25-xs-rear-tire`.
**What happened:** When the right tube or tire depends on a size the catalog can't know, the agent drafted labor only instead of asking for the size on the sidewall.
**Root cause:** prompt issue (e03 also overlaps the frame-size data gap, D-017).
**Fix:** not addressed directly; no experiment targeted it. E-006's generic tube, sized at the bench, means a missing size no longer leaves a flat repair without a tube line, but the agent is not prompted to ask for the size.

## F-008: Says "disagree" while blaming the staff's own area
**Found in:** E-001 / 7 cases, e.g. `n11-supercaliber-tubeless-sealant` and `n03-checkpoint-slow-shifts` (3/3).
**What happened:** The agent's own top cause sat inside the area staff picked, and it still marked disagree; once its stated reason was the literal word "placeholder".
**Root cause:** triage error; "agree" was undefined in the prompt (Justin defined it in step 16: agree means the problem is in staff's area).
**Fix:** fixed in E-005 (D-039): the prompt defines agreement as Justin did, triage names `likely_area`, and code sets agreement from it. Self-contradicting cases (`n11`, `s02`, `s08`) are 3/3 by construction. Overall `agreement_correct` barely moved (0.83 to 0.82): the check is now too strict for adjacent areas (derailleur and hanger), which is an open follow-up.

## F-009: Draft lines don't hang together
**Found in:** E-001 / 6 cases, e.g. `c01-hightower-squeak-grinding` and `s05-caad10-concave-rim` (3/3).
**What happened:** Parts drafted without the labor to fit them, and ROTOR-TRUE on a rotor being replaced. The same errors appeared in step 10b's first live runs.
**Root cause:** prompt issue; nothing in code enforces coherence.
**Fix:** fixed in E-004 (D-038): `draft_work_order` rejects a part without the labor that fits it, and labor that works on a part being replaced, and says what to change. `line_coherence` is 1.00 on every slice from then on. The evaluator keeps its own copy of the rules, so it still checks independently.

## F-010: Diagnosis contradicts the bike's specs or the shop's guidance
**Found in:** E-001 / 9 cases, caught mostly by the diagnosis judge.
**What happened:** A press-fit diagnosis on a BSA threaded shell (`m06`), cable stretch on electronic Di2 shifting (`n15`), rim damage on disc brakes (`c01`), a weld on a carbon frame (`s02`), rotor bolts on centerlock rotors (`c04`), ignoring the shop's once-per-turn and pedals-first guidance (`n09`, `n10`), a loose headset for bars that move separately from the wheel (`s06`).
**Root cause:** triage error: the facts were in the prompt.
**Fix:** open. Never targeted: the plan was to measure it first (a spec self-check before the diagnosis is accepted), and no experiment did. The diagnosis judge still catches these.

## F-011: Won't draft a part it can't fully confirm
**Found in:** E-001 / `e11-topstone-wider-tires`, `m06-topfuel-standing-creak-correct` (3/3); also the flat repairs with no tube line.
**What happened:** Drafted INSPECT only instead of the part flagged unverified. Justin: any flat repair or tire install needs a tube line (or a tubeless setup), even a generic, unsized one.
**Root cause:** prompt issue plus a data gap (no generic tube part in the catalog).
**Fix:** fixed in E-006 (D-040): a generic tube (`tube-generic`, always reported unknown by the compatibility engine, so drafted flagged unverified), a flats doc saying every tubed repair needs a tube, and a draft prompt that drafts an unconfirmed part rather than leaving it out. `parts_categories_present` rose from 0.62 to 0.89.

## F-012: Rim width isn't in the data
**Found in:** E-001 / edge / `e09-fuelex-road-slicks` (3/3).
**What happened:** The agent said 700x25 road slicks fit a 30 mm internal MTB rim and drafted them. Only the judges and the forbidden-parts list caught it.
**Root cause:** data gap, known and deferred (D-020).
**Fix:** unfixed by design for now.

## F-013: Labels that were wrong or undefined
**Found in:** step 16 review of E-001.
**What happened:** 17 cases changed after review: three severities where the shop's own docs disagreed with the labels (the docs win: oil on a rotor, grinding and contaminated pads are safety-critical); four agreement labels once "agree" was defined; three agreement labels that can't be judged before an inspection (no longer scored); wet-weather squeal is normal; two expected questions that wouldn't change the order; a parts-only purchase that shouldn't be a work order; a tube-or-tubeless question on the sidewall bulge. One evaluator, `labor_forbidden_absent`, turned out to have nothing to check: no case sets forbidden labor, so it can't fail.
**Root cause:** label question (labels written before the agent's behavior showed where definitions were missing).
**Fix:** applied through the `REVIEW` table in `build_e2e.py` (raw labels untouched); E-001 re-scored offline as E-001b. `labor_forbidden_absent` stays, and can only show something once cases set forbidden labor.

## F-014: Explanation judge gaps found in review
**Found in:** step 16 review.
**What happened:** Justin sided with the explanation judge on invented findings, unexplained jargon and mentioning checks that aren't on the order, but not on hedged likely causes ("this usually means...") or on promising a tube for a flat repair. It also failed true shop facts it wasn't given (the inspection fee is waived when work is booked).
**Root cause:** judge rubric (too strict on hedges; missing shop facts and the tube rule).
**Fix:** rubric v3 (D-042, C-001): hedges, shop facts and jargon no longer fail; diagnosis judge held-out kappa 0.60. The explanation judge still misses Justin's rare fails (held-out kappa -0.20).

## F-015: A dropped connection lost three runs, and the reports choked on it
**Found in:** E-006 (`8d43b45-e2e-454b7b83`).
**What happened:** OpenRouter closed connections mid-response for a few seconds; three agent runs and two diagnosis-judge calls failed. Their evaluators recorded error entries under their own names (`deterministic`, and `adapter` for the judges, a naming bug), and `report.py`, which expected every run to have every key that any run had, then called all 183 good runs incomplete.
**Root cause:** other (eval tooling, plus no retry on transient network errors in the agent).
**Fix:** `report.py` and `rescore.py` leave out errored runs and list them; expected scores are the keys most runs have; `--allow-missing` reports with each gap listed; judge adapters carry their real names. Unfixed: the agent doesn't retry a dropped connection (a step 17 candidate on reliability, separate from quality).

## F-016: Over-escalation while a braking question is still open
**Found in:** E-002 to E-006 / `a02-fuelex-skip-inspection-lever` (3/3), `e10-fuelex-swapped-sram-brakes` (3/3), `m02-roscoe-play-when-braking` (3/3); the mirror case `c02-stumpjumper-squeak-is-brakes` (missed 3/3).
**What happened:** With the never-release list always in view, the agent escalates a lever to the bar while asking whether the bike still stops (a02), and "pads are worn out" as worn to the wear line (e10). The labels say needs service plus a question for a02, needs service for e10, needs service for m02 (D-031), but safety-critical for c02, where whether braking is affected is equally unknown.
**Root cause:** label question: the labels don't follow one rule for "braking may be compromised, unknown until answered".
**Fix:** Justin's policy: "we default to safety if we're not sure." a02, e10 and m02 relabeled safety-critical (E-006b: no over-escalations left); the agent still holds c02 at needs service while asking. E-007 put the policy in the triage prompt: `c02` is still missed 3/3 and `e10` 2/3. E-008 repeated E-007 and got the same misses: the change is real, and it is a swap (`s04` fixed, `e10` broken), not a closing of the gap. Asking triage for a JSON schema instead (E-009) catches both but over-escalates seven other cases.

## F-017: Eval infrastructure limits dropped runs
**Found in:** E-009 (first attempt and rerun) and E-010, while building the frontier-model comparison.
**What happened:** Two limits nobody had looked at ended runs part-way. (1) LangSmith's workspace limit on monthly traces (a user-defined cap, 14,000 at first; the account's usage card showed 13,710 against its 5,000 included traces, which is not the same number): once it was reached, uploads were rejected with 429s while the run itself carried on. The first E-009 lost 63 of 186 runs and all their scores, and the rerun lost seven more in its first minutes, before a raised cap took effect. (2) OpenRouter reserves a large model's worst-case cost for every request in flight, so with four examples at a time on Opus 5.5 and about $20 of balance left, 92 of 186 runs were refused with HTTP 402, although the balance was never close to zero. The refused requests did not show up in the key's usage; the ones that completed cost $7.87.
**Root cause:** other (eval tooling and account limits): the runner treats a failed upload or a refused request as an ordinary per-run problem and carries on, so a run can spend its budget and record half of it.
**Fix:** none in the runner yet. The mitigation used for E-010 was a watchdog that polled LangSmith's reject flag and stopped the run if uploads began being refused (it never fired). The comparison is reported as partial (94 of 186 runs, at least one per case, no spreads) rather than rerun for about $8 more. What the runner should do: stop on the first rejected upload, run big models at lower concurrency, and check balance against the expected cost before starting.

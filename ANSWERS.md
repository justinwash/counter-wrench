# Answers

Spoilers for `EXERCISES.md`. For each branch: what changed, why the agent misbehaves, how you'd find it, the fix, and how to stop it coming back.

"Tests" below means `make test` with Postgres running (`make up`). Without Postgres, about 170 database tests are skipped, and all seven branches pass. With Postgres, three branches fail one test each; four pass everything.

| Branch | Level | Where | Caught by `make test`? |
| --- | --- | --- | --- |
| `debug/01` | Subtle | Triage prompt | No |
| `debug/02` | Subtle | Knowledge doc heading (data, not code) | Only with Postgres: `test_graph::test_every_row_sees_the_never_release_list` |
| `debug/03` | Moderate | `retrieve` node | No |
| `debug/04` | Moderate | API question-round bookkeeping | Only with Postgres: `test_api::test_triage_stops_asking_after_two_rounds_and_tells_the_mechanic` |
| `debug/05` | Severe | Draft validator's install-labor table | No |
| `debug/06` | Catastrophic | Order severity in the graph | No |
| `debug/07` | Catastrophic | API entrypoint skips the redacted intake | Only with Postgres: `test_api::test_guardrails_run_before_the_graph` |

---

## debug/01: the prompt stopped saying "default to safety"

**Change.** `src/counterwrench/agent/prompts/triage.md`. Commit "tighten wording". This line:

> If you're not sure: when braking, steering or wheel retention might be compromised and the answer isn't known yet, it's safety-critical until a mechanic checks it. Ask your question too, but don't lower the severity while waiting for the answer.

became:

> If you're not sure whether braking, steering or wheel retention is affected, ask your question and set the severity from what the evidence shows so far.

A harmless rewording of the bike-specs line sits next to it in the same commit.

**Why the agent misbehaves.** The new line reads as reasonable, but it reverses the shop's policy (D-041, E-007): uncertainty about brakes used to mean safety-critical, and now it means "rate what you can see". On an ambiguous brake complaint ("squeaks, not sure since when") the model asks its question and rates it `needs_service`. The line "when evidence conflicts... choose the more severe reading" is still there, so most brake jobs still escalate. That's why it's subtle: only the uncertain ones slip.

**How you'd find it.**
- `make eval`, safety slice: `safety_escalated` and `no_unsafe_release` drop on the uncertain cases (`c02`, `e10`, `s04`, and similar). Run it three times; one run is within the noise.
- In the trace, the triage output has a `question_for_customer` and a non-critical severity together. On `main`, a brake row with an open question stays safety-critical.
- `git log -p -- src/counterwrench/agent/prompts/` once you suspect the prompt.

**Fix.** Restore the line.

**Prevent it.** Treat prompts like code: any prompt change runs the eval (the repo's "one change per experiment" rule), with the safety slice as a gate that blocks a merge when it drops. Better still, enforce the rule in code: in `route`, a row whose `likely_area` is brakes, steering or wheels and that still has an open question gets raised to safety-critical, whatever the model said.

**Lesson.** Prompt regressions are silent, probabilistic and partial. You need repeated evals per slice to see them, not a few manual tries.

---

## debug/02: the pinned safety policy silently disappeared

**Change.** `data/docs/policy-safety.md`: the heading `## What we never release` became `## What we never hand back` (plus a small rewording). The retrieval eval set was find-and-replaced to the new id so `test_datasets` stays green. `ALWAYS_INCLUDED` in `agent/nodes.py` still says `policy-safety#what-we-never-release`.

**Why the agent misbehaves.** Chunk ids are built from headings (`doc_id#anchor`). After `make seed`, the old id doesn't exist. `get_chunks` skips missing ids without a word, so the never-release list is no longer pinned to every row, and it comes back only when similarity search finds it (4 of 63 rows when this was measured, F-002). The model loses the shop's safety list and grows less strict.

**How you'd find it.**
- In a triage trace, the `<knowledge>` blocks no longer include the safety policy, and `citations` rarely mention `policy-safety`.
- `python -m counterwrench.rag.search "brake lever to the bar"` and checking the ids, or `SELECT id FROM doc_chunks WHERE id LIKE 'policy-safety%'`.
- `git log` shows only a docs change, which is the trap: nobody looks at a docs commit for a behavior change.
- `make test` without Postgres is green. With Postgres, `test_every_row_sees_the_never_release_list` fails, because it runs against the seeded knowledge base.

**Fix.** Revert the heading, or update `ALWAYS_INCLUDED` to the new anchor.

**Prevent it.** Make the pinned lookup loud: `get_chunks` (or startup, or `make doctor`) raises if a pinned id is missing. Add a test that every id in `ALWAYS_INCLUDED` exists in `data/docs`. The docstring in `rag/docs.py` already says headings must stay stable; a check should enforce it.

**Lesson.** Silent fallbacks hide failures. Content is configuration: a docs edit can change the agent's behavior as much as a code edit.

---

## debug/03: every row gets the same knowledge

**Change.** `retrieve` in `agent/nodes.py` now runs one search for the whole intake (all rows' text joined) and gives that same list of chunks to every row. The comment calls it a saving on embeddings.

**Why the agent misbehaves.** It's still five chunks, but now for two or three complaints together. Vector search over a mixed query favors whichever complaint dominates the text, so the other rows get little or no relevant knowledge, plus chunks about another complaint. The model says "assess row r2 only", but its evidence is about r1, so it gives a vague diagnosis or names the wrong system, and cites chunks that are valid ids but irrelevant. Intakes with one complaint are unaffected, which is why the demo looks fine.

**How you'd find it.**
- Open a multi-row trace: every `triage_row` branch has the same `<knowledge>` blocks.
- Diagnosis judge and `agreement_correct` fall on multi-row cases only. Slicing eval results by number of rows shows it.
- No test checks that rows get different chunks.

**Fix.** Revert to one search per row.

**Prevent it.** A graph test with two unrelated rows that asserts each row's chunks match its own complaint. Measure retrieval per row in the evals. Count the cost saving against the quality loss before shipping it.

**Lesson.** Context engineering is part of the system. A performance refactor can quietly degrade what the model sees.

---

## debug/04: the agent keeps asking the same question

**Change.** `add_answers` in `api/intakes.py`: the round count is now `{**prior.question_rounds, **dict.fromkeys(new, 1)}`. Every row answered this round is set to 1, never 2 or more.

**Why the agent misbehaves.** The cap (`MAX_QUESTION_ROUNDS = 2` in `triage_row`) never fires, because no row ever reaches 2 rounds. The prompt says "don't ask what was answered", but for an uncertain complaint like squealing brakes the model finds a new angle each round. That's the exact loop this cap was built to stop (the docstring and README describe it). The backstop is in code because the prompt alone didn't hold.

**How you'd find it.**
- Reproduce in the UI: answer three times; the fourth triage still asks.
- In the intake state, `question_rounds` stays at `{"r1": 1}` however many rounds pass.
- `make prod-report` shows the "question-limit rate" falling to zero, a monitoring clue.
- With Postgres, `test_triage_stops_asking_after_two_rounds_and_tells_the_mechanic` fails. Without Postgres it's skipped, and the one pure test of `add_answers` checks a single round, where 1 is correct.

**Fix.** `rounds[row_id] = rounds.get(row_id, 0) + 1` for each answered row.

**Prevent it.** Keep a fast unit test for the bookkeeping across several rounds, not just one (the existing pure test checks only one round, where 1 is right). Alert when the question-limit rate drops to zero.

**Lesson.** A model told "don't loop" still loops. Hard limits in code are the backstop, and their state has to be right.

---

## debug/05: contradictory tool feedback makes the agent ping-pong

**Change.** `INSTALL_LABOR` in `tools/work_orders.py` was "grouped by system", and `BRAKE-PAD-INSTALL` became `BRAKE-PADS-INSTALL`, a code that isn't on the service menu.

**Why the agent misbehaves.** The draft validator now gives contradictory feedback:
1. The model drafts pads with `BRAKE-PAD-INSTALL`: rejected, "add the labor that fits it (BRAKE-PADS-INSTALL)".
2. It adds `BRAKE-PADS-INSTALL`: rejected, "Unknown labor code 'BRAKE-PADS-INSTALL'; use search_labor_menu" (unknown codes are checked before coherence, so the coherence error disappears).
3. Search returns `BRAKE-PAD-INSTALL`, the draft prompt also says "pads need BRAKE-PAD-INSTALL", and the model goes back to step 1.

It loops until `MAX_DRAFT_STEPS` (10 model turns), then gives up: no draft, `needs_mechanic`, and about 10 times the drafting cost. The mechanic's line editor uses the same validator, so a human can't add pads either.

**How you'd find it.**
- The drafting trace: `draft_work_order` called many times, rejected each time with alternating problems.
- Eval: `order_created_when_expected` drops on every pad case; cost and latency per run go up.
- Every brake-pad job fails, and nothing else does.
- No test catches it: no test drafts brake pads through the real validator, and nothing checks the table against the service menu.

**Fix.** `"brake_pads": {"BRAKE-PAD-INSTALL"}`.

**Prevent it.** A test that every code in `INSTALL_LABOR` exists in `data/seed/labor_menu.yaml`, and one that the tool's table matches the evaluator's copy in `evals/evaluators/draft.py`. In the loop, stop early and hand off when the same tool rejects the agent repeatedly.

**Lesson.** When an agent loops, check the tool feedback first: the model may be doing exactly what each message tells it. A step cap limits the damage but can hide the cause.

---

## debug/06: a "don't ride" bike becomes a cosmetic order

**Change.** `order_severity` in `agent/nodes.py`, used by `draft` and `record_decline_node` in place of `models.max_severity`:

```python
return max((a.severity for a in assessments.values()), key=list(Severity).index)
```

**Why the agent misbehaves.** `Severity` is declared most severe first, so a higher index means less severe, and `max` picks the mildest row. With one row nothing changes. With "lever to the bar" (safety-critical) plus "scuffed top tube" (cosmetic):
- `route` still escalates (it checks each row), so the counter screen shows DO NOT RIDE.
- `save_draft` overwrites the severity with the code-computed value, so the saved order is **cosmetic**, whatever the model put in `draft_work_order`, and it sorts last in the mechanic's queue.
- A declined order is recorded as cosmetic. The API still asks for a waiver because it checks `escalated`, but the record contradicts it.

The model did the right thing; code overrode it with the wrong answer.

**How you'd find it.**
- Compare the triage outputs in the trace (r1 `safety_critical`) with the saved order's severity: they disagree, so look at what sets it.
- The tool call's arguments are right, so the change happens after the tool call, in `save_draft`.
- Eval: order-level safety checks fail on multi-row safety cases; single-row cases pass.
- Unit tests pass: `max_severity` is tested, but `order_severity` isn't.

**Fix.** Use `max_severity(...)`, the tested single source of truth.

**Prevent it.** Don't reimplement ordering logic. Add a graph test with mixed severities that checks the saved order. Add an invariant: an order from an escalated run must be safety-critical (a DB check or an online evaluator).

**Lesson.** "The model got it wrong" is a hypothesis. Check the trace for where the right answer turned wrong, which here is deterministic code after the model.

---

## debug/07: PII reaches the model and public traces

**Change.** `_new_run` in `api/intakes.py` was "reformatted" to one key per line, and `"intake": guarded.intake` became `"intake": intake`, the raw input.

**Why it's catastrophic.** Guardrails still run, so `pii_counts` is right and the run metadata says `pii_redacted: {"phone": 1}`, but the graph gets the unredacted intake. Phone numbers, emails and names go to the model provider, to LangSmith (whose traces this project shares publicly), to the graph checkpoint, and into the saved order's `intake` JSON. The model may repeat the name in `customer_explanation`. The CLI (`agent/run.py`) is unaffected, so a local repro with the CLI shows redaction working.

**How you'd find it.**
- Open the trace: the graph input contains the phone number, while the metadata says it was redacted. The metadata reports what the guardrail found, not what the graph received.
- Compare entrypoints: the CLI passes `guarded.intake`, the API passes `intake`.
- The online PII evaluator may flag outputs that repeat PII.
- `test_guardrails` passes because the function is fine; the call site is wrong.
- With Postgres, `test_api::test_guardrails_run_before_the_graph` fails. Without Postgres it's skipped, so a quick `make test` looks green.

**Fix.** Pass `guarded.intake`. Then handle the incident: delete or un-share the affected traces, purge the stored intakes and checkpoints, and decide who has to be told.

**Prevent it.** Make the unsafe call impossible: the graph accepts only a `RedactedIntake` type that only `apply_guardrails` can build. Add an API test that sends PII and asserts the graph's input and the saved order contain none. Redact again as a last line of defense in the tracer.

**Lesson.** A guardrail at the boundary has to cover every entrypoint. Telemetry that reports what a check found can make a failed control look like it worked.

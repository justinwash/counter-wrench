# Debugging exercises

Seven branches, each with one planted bug that makes the agent (or the system around it) do something unexpected or unwanted. They run from subtle to catastrophic. Each branch forks from this one, so `EXERCISES.md` is on every branch.

Treat each one like a bug report from the shop: start from the symptom, reproduce it, find the root cause, fix it, and say how you'd stop it coming back. Try not to diff the branch against `main` first; work from traces, evals, tests and the code.

The answers are on the `debug-exercises-answers` branch (`ANSWERS.md`).

## Setup

```sh
git checkout debug/01          # pick a branch
cp .env.example .env           # one model key; LANGSMITH_API_KEY for traces
make start                     # or: make up && make seed && make api
make test                      # unit tests (some need Postgres: make up)
```

Some bugs only show after `make seed` (it re-ingests the knowledge base). Useful tools: the LangSmith trace for each run, `python -m counterwrench.agent.run data/samples/<file>.json`, `python -m counterwrench.rag.search "<query>" --bike <id>`, `make eval` and its per-slice results.

## The tickets

| Branch | Level | Report from the shop |
| --- | --- | --- |
| `debug/01` | Subtle | "Since last week's update, a couple of brake jobs where the customer wasn't sure what was wrong came through as 'needs service' instead of 'don't ride'. Most brake jobs still look fine." |
| `debug/02` | Subtle | "Nothing's crashing, but the agent seems less strict about safety than it used to be, and it hardly ever cites the safety policy any more. It started after the docs were tidied up and re-seeded." |
| `debug/03` | Moderate | "One-complaint intakes look great. When a customer has two or three unrelated problems, the diagnosis for the second and third complaints is vague or talks about the wrong part of the bike." |
| `debug/04` | Moderate | "A customer with squealing brakes got asked basically the same question four times. Staff answered every time. It never moved on." |
| `debug/05` | Severe | "Any job that needs new brake pads ends with 'the drafting agent ended without a saved draft; a mechanic must write it'. The bill for model calls went up too. When a mechanic tries to add pads to an order by hand, the edit is refused." |
| `debug/06` | Catastrophic | "A bike came in with a lever going to the bar and a scuffed top tube. The counter screen said DO NOT RIDE, but the work order says cosmetic and was at the bottom of the mechanic's queue." |
| `debug/07` | Catastrophic | "A customer found their phone number in a public LangSmith trace link we shared. The run metadata says PII was redacted." |

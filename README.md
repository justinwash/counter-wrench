# CounterWrench

A front-of-house service intake tool for bike shops. Counter staff pick the customer's bike and log each complaint on a POS-style form. An agent triages each complaint, checks parts compatibility with deterministic code, and drafts a work order that a mechanic must approve before anything is committed.

> **Status:** work in progress. This README will grow into the full reviewer guide (results, architecture, evals, failures, production evaluation).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you)
- GNU Make
- Docker with Compose v2, running

## Development

```sh
make install   # create .venv and install dependencies
make doctor    # check keys, resolved models, and live tool-calling/structured-output calls
make up        # start Postgres + pgvector and wait until healthy
make down      # stop Postgres (data is kept)
make db-reset  # stop Postgres and delete its data
make psql      # open a psql shell in the database
make lint      # ruff check + format check
make format    # apply ruff fixes and formatting
make test      # run pytest
```

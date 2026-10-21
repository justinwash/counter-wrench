# Each recipe is a single command so it runs the same under sh, cmd and PowerShell.
# Targets are added by the step that makes them work; none are placeholders.

.PHONY: install lint format test doctor up down db-reset psql migrate seed ingest trace-check studio upload-datasets judge-smoke eval eval-report eval-rescore api db-ui api-types ui ui-test start prod-report prod-harvest

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest

doctor:
	uv run python -m counterwrench.doctor

trace-check:
	uv run python -m counterwrench.trace_check

# Postgres only, for development (the app runs on your machine: make api, make ui).
up:
	docker compose up -d --wait db

down:
	docker compose down

db-reset:
	docker compose down -v

psql:
	docker compose exec db psql

migrate:
	uv run python -m counterwrench.db.migrate

seed: migrate
	uv run python -m counterwrench.db.seed
	uv run python -m counterwrench.rag.ingest

ingest:
	uv run python -m counterwrench.rag.ingest

studio:
	uv run langgraph dev

upload-datasets:
	uv run python -m evals.datasets.upload

judge-smoke:
	uv run python -m evals.judge_smoke

# make eval ARGS="--scratch --limit 6 --repetitions 1" for a pilot
eval:
	uv run python -m evals.runner $(ARGS)

eval-report:
	uv run python -m evals.report $(EXP)

eval-rescore:
	uv run python -m evals.rescore $(EXP)

api:
	uv run uvicorn counterwrench.api.app:app --port 8000

# pgAdmin at http://localhost:5050, already connected to the CounterWrench database.
db-ui:
	docker compose --profile tools up -d --wait pgadmin

# Regenerate the frontend's API types after changing a route or model.
api-types:
	uv run python -m counterwrench.api.openapi frontend/openapi.json
	npm --prefix frontend run gen:api

# The intake UI with hot reload at http://localhost:5173 (run `make api` alongside it).
ui:
	npm --prefix frontend run dev

ui-test:
	npm --prefix frontend test

# Everything in Docker, the reviewer path: http://localhost:8000
start:
	docker compose up -d --build --wait db app

# How the live agent is doing: mechanic decisions, thumbs, escalations, scores, cost. Reads the
# database in .env; on the server run it inside the app container (see the README).
prod-report:
	uv run python -m counterwrench.online.report

# Live orders worth labeling (rejected, edited, thumbs) -> harvest.yaml for you to label.
# Never added to a dataset by code.
prod-harvest:
	uv run python -m counterwrench.online.harvest

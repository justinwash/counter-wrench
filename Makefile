# Each recipe is a single command so it runs the same under sh, cmd and PowerShell.
# Targets are added by the step that makes them work; none are placeholders.

.PHONY: install lint format test doctor up down db-reset psql migrate seed ingest trace-check studio upload-datasets judge-smoke eval eval-report eval-rescore api db-ui

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

up:
	docker compose up -d --wait

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

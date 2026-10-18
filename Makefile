# Each recipe is a single command so it runs the same under sh, cmd and PowerShell.
# Targets are added by the step that makes them work; none are placeholders.

.PHONY: install lint format test doctor up down db-reset psql

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

up:
	docker compose up -d --wait

down:
	docker compose down

db-reset:
	docker compose down -v

psql:
	docker compose exec db psql

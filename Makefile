# Each recipe is a single command so it runs the same under sh, cmd and PowerShell.
# Targets are added by the step that makes them work; none are placeholders.

.PHONY: install lint format test

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

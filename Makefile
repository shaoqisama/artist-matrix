UV ?= uv

.PHONY: verify lint format type-check test

verify: lint type-check test

lint:
	$(UV) run ruff check src tests

format:
	$(UV) run ruff format src tests

type-check:
	$(UV) run mypy src

test:
	$(UV) run pytest

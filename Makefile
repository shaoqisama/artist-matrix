UV ?= uv

.PHONY: verify verify-all lint format type-check test test-integration test-all

# Default verify runs unit tests only (skip integration)
verify: lint type-check test

# Full verify runs both unit and integration tests
verify-all: lint type-check test test-integration

lint:
	$(UV) run ruff check src tests

format:
	$(UV) run ruff format src tests

type-check:
	$(UV) run mypy src

# Unit tests only (skip @pytest.mark.integration)
test:
	$(UV) run pytest -m "not integration"

# Integration tests (may require network/API keys)
test-integration:
	$(UV) run pytest -m "integration"

# Convenience target to run both suites locally
test-all: test test-integration

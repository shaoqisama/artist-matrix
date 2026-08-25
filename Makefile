UV ?= uv

.PHONY: verify verify-all lint format format-check type-check test test-integration test-external test-all

# Default verify runs unit tests only (skip integration)
verify: lint format-check type-check test

# Full verify runs both unit and integration tests
verify-all: lint format-check type-check test test-integration

lint:
	$(UV) run ruff check src tests

format:
	$(UV) run ruff format src tests

format-check:
	$(UV) run ruff format --check src tests

type-check:
	$(UV) run mypy src

# Unit tests only (skip deterministic integration and credentialed external tests)
test:
	$(UV) run pytest -m "not integration and not external"

# Deterministic cross-component integration tests
test-integration:
	$(UV) run pytest -m "integration"

# Opt-in tests that require network access or credentials
test-external:
	$(UV) run pytest -m "external"

# Convenience target to run both suites locally
test-all: test test-integration

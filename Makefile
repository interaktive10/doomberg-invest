# Doomberg Invest — task runner (BRIEF Appendix A "Commands").
SHELL := /bin/bash
export DATABASE_URL ?= postgresql://doom:doom@localhost:5432/doom
UV := uv run --frozen
MILESTONES := m0 m1 m2 m3 m4 m5 m6 m7 m8 m9

.PHONY: setup test lint type guard protected migrate-dev fixtures universe thesis-validate $(addprefix verify-,$(MILESTONES))

setup:            ## install Python 3.12 + locked deps (and web deps once web/ exists)
	uv python install 3.12
	uv sync --frozen
	@if [ -f web/pnpm-lock.yaml ]; then cd web && pnpm install --frozen-lockfile; fi

test:             ## offline test suite (never touches the network)
	MOCK_EXTERNALS=true $(UV) pytest

lint:
	$(UV) ruff check .
	$(UV) ruff format --check .

type:
	$(UV) mypy

guard:            ## BRIEF Appendix E
	$(UV) python scripts/guard.py

protected:        ## BRIEF Appendix D, against origin/main; LABELS="a,b"
	$(UV) python scripts/protected_check.py --base origin/main --labels "$(LABELS)"

migrate-dev:
	@if [ -f pipeline/db/migrate.py ]; then $(UV) python -m pipeline.db.migrate; \
	else echo "migrate-dev: pipeline/db/migrate.py arrives in M1" >&2; exit 1; fi

universe:         ## M0: fetch universe snapshots (network) and resolve the capex seed
	$(UV) python scripts/fetch_fixtures.py universe
	$(UV) python scripts/resolve_capex_seed.py --write

fixtures:         ## one-time network fetch of test fixtures (BRIEF §9)
	$(UV) python scripts/fetch_fixtures.py universe

thesis-validate:
	@if [ -f pipeline/thesis/validate.py ]; then $(UV) python -m pipeline.thesis.validate --week "$(WEEK)"; \
	else echo "thesis-validate: pipeline/thesis/validate.py arrives in M6" >&2; exit 1; fi

$(addprefix verify-,$(MILESTONES)): verify-%:
	$(UV) python scripts/verify.py --milestone $*

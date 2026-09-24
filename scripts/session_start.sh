#!/bin/bash
# Cloud sessions only; idempotent; fast. DATABASE_URL defaults live in the Makefile and pipeline/settings.py.
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then exit 0; fi
cd "$CLAUDE_PROJECT_DIR" || exit 0
service postgresql start >/dev/null 2>&1 || true
su postgres -c "psql -tc \"select 1 from pg_roles where rolname='doom'\" | grep -q 1 || psql -c \"create role doom login password 'doom' superuser\"" >/dev/null 2>&1 || true
su postgres -c "psql -tc \"select 1 from pg_database where datname='doom'\" | grep -q 1 || createdb -O doom doom" >/dev/null 2>&1 || true
uv python install 3.12 >/dev/null 2>&1 || true
[ -f pyproject.toml ] && (uv sync --frozen >/dev/null 2>&1 || uv sync >/dev/null 2>&1) || true
[ -f web/pnpm-lock.yaml ] && (cd web && pnpm install --frozen-lockfile >/dev/null 2>&1) || true
[ -f pipeline/db/migrate.py ] && uv run python -m pipeline.db.migrate >/dev/null 2>&1 || true
exit 0

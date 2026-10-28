"""The digest's stale banner (BRIEF §2.7, §4.12) names only the sources with an SLA in config/staleness.yaml, like the
app's Home banner (overhaul PR 4, docs/SPEC_ISSUES.md 52): a dead source's leftover health row (yahoo, stooq, fred,
eia, gdelt), stale or not, stays in the Source health table but never in the banner."""

from __future__ import annotations

from datetime import UTC, datetime

from pipeline.db.models import SourceHealth
from pipeline.digest import weekly as digest

NOW = datetime(2026, 11, 7, 3, tzinfo=UTC)
OLD = datetime(2026, 9, 1, 6, tzinfo=UTC)


def test_dead_sources_are_never_in_the_banner_but_stay_in_the_table() -> None:
    sla = digest.sla_days()
    assert set(sla) == {"sec", "twelvedata", "sec_13f", "nse", "bse"}  # India back (SPEC_ISSUES 55)
    dead = [SourceHealth(source=s, last_success=OLD, last_error="stale: gone", stale=True)
            for s in ("yahoo", "stooq", "fred", "eia", "gdelt")]  # fmt: skip
    assert digest.banner(dead, NOW, sla) == []
    assert [line.split(" | ")[0] for line in digest.health(dead, NOW, sla)[2:]] == [
        "| yahoo", "| stooq", "| fred", "| eia", "| gdelt"]  # fmt: skip


def test_sources_with_an_sla_are_named_when_stale_or_late() -> None:
    sla = digest.sla_days()
    rows = [SourceHealth(source="stooq", stale=True),
            SourceHealth(source="sec", last_success=NOW, stale=True),
            SourceHealth(source="twelvedata", last_success=OLD)]  # fmt: skip
    banner = digest.banner(rows, NOW, sla)
    assert banner[0].startswith("**Stale data:** sec (stale), twelvedata (no success for 66 days; SLA 8).")
    assert "stooq" not in banner[0]

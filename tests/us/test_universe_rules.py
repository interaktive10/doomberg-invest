"""US universe rules (BRIEF §1.3) applied by the weekly run: first failing rule wins; REITs are kept."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import yaml

from pipeline.settings import REPO_ROOT
from pipeline.us.submissions import Filing, Submissions
from pipeline.us.universe import UniverseRules, decide, sector_for_sic

TODAY = date(2026, 9, 20)
RULES = UniverseRules.load(REPO_ROOT)
SECTORS = yaml.safe_load((REPO_ROOT / "config" / "sectors.yaml").read_text(encoding="utf-8"))["us_sic_ranges"]


def filing(form: str, day: date) -> Filing:
    return Filing(f"acc-{form}-{day}", form, day, None, datetime(day.year, day.month, day.day, 21, tzinfo=UTC), (), "")


def subs(exchanges: tuple[str, ...] = ("NYSE",), sic: str | None = "3571", forms: tuple[str, ...] = ("10-Q",),
         filed: date = date(2026, 8, 1)) -> Submissions:  # fmt: skip
    return Submissions("0000000001", "Test Co", "operating", sic, None, "1231", ("TST",), exchanges,
                       tuple(filing(f, filed) for f in forms))  # fmt: skip


BIG = Decimal(60_000_000)


@pytest.mark.parametrize(
    ("s", "ttm", "reason"),
    [
        (subs(), BIG, None),
        (subs(exchanges=("Nasdaq",)), BIG, None),
        (subs(sic="6798"), BIG, None),  # REITs are kept (docs/DECISIONS.log)
        (subs(exchanges=("OTC",)), BIG, "not listed on NYSE/Nasdaq"),
        (subs(exchanges=()), BIG, "not listed on NYSE/Nasdaq"),
        (subs(sic="6770"), BIG, "SPAC (SIC 6770)"),
        (subs(sic="6726"), BIG, "fund (SIC 6726)"),
        (subs(sic="6792"), BIG, "royalty/grantor trust (SIC 6792)"),
        (subs(forms=("10-Q", "20-F")), BIG, "foreign private issuer (20-F/40-F filer)"),
        (subs(forms=("8-K",)), BIG, "no 10-K/10-Q in the last 15 months"),
        (subs(filed=date(2025, 6, 1)), BIG, "no 10-K/10-Q in the last 15 months"),  # 476 days ago
        (subs(forms=("10-K/A",)), BIG, None),  # an amendment still shows the company files
        (subs(), None, "TTM revenue unknown"),
        (subs(), Decimal(49_999_999), "TTM revenue 49,999,999 < 50,000,000"),
        (subs(), Decimal(50_000_000), None),
    ],
)
def test_decide(s: Submissions, ttm: Decimal | None, reason: str | None) -> None:
    d = decide(s, ttm, RULES, TODAY)
    assert (d.in_universe, d.reason) == (reason is None, reason)


def test_rules_come_from_config() -> None:
    assert RULES.exchanges == {"nyse", "nasdaq"} and RULES.min_ttm_revenue_usd == Decimal(50_000_000)
    assert RULES.foreign_forms == {"20-F", "40-F"} and "6798" not in RULES.trust_sic


@pytest.mark.parametrize(
    ("sic", "sector"),
    [("3571", "technology"), ("3531", "industrials"), ("6512", "real_estate"), ("6021", "financials"),
     ("4911", "utilities"), ("1311", "energy"), ("9999", None), (None, None), ("", None), ("12a", None)],
)  # fmt: skip
def test_sector_for_sic_takes_the_narrowest_range(sic: str | None, sector: str | None) -> None:
    assert sector_for_sic(sic, SECTORS) == sector

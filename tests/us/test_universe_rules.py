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
         filed: date = date(2026, 8, 1), tickers: tuple[str, ...] = ("TST",)) -> Submissions:  # fmt: skip
    return Submissions("0000000001", "Test Co", "operating", sic, None, "1231", tickers, exchanges,
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


def test_common_stock_must_be_listed() -> None:
    """Review F6: filers listed only through preferred shares or notes are not common-stock listings (§1.3)."""
    from pipeline.us.universe import PublicFloat, public_float

    pref = subs(tickers=("SCE-PB", "SCE-PC", "SCE-PD"))
    assert decide(pref, BIG, RULES, TODAY).reason == "no common stock listed (preferred series only)"
    assert decide(subs(tickers=("BRK-A", "BRK-B")), BIG, RULES, TODAY).in_universe  # share classes, not preferred
    gpja = subs(tickers=("GPJA",), forms=("10-Q", "10-K"), filed=date(2024, 11, 1))  # a periodic filer for years
    sub = decide(gpja, BIG, RULES, TODAY, PublicFloat(Decimal(0), date(2025, 6, 30)))  # a subsidiary's listed notes
    assert sub.reason == "no public common equity (10-K public float 0)"
    assert decide(subs(), BIG, RULES, TODAY, None).in_universe  # not reported yet (a new registrant): no exclusion
    cf = {"facts": {"dei": {"EntityPublicFloat": {"units": {"USD": [
        {"end": "2023-06-30", "val": 5e9, "form": "10-K", "filed": "2024-02-20"},
        {"end": "2024-06-30", "val": 0, "form": "10-K", "filed": "2025-02-20"},
        {"end": "2024-06-30", "val": 7e9, "form": "S-1", "filed": "2025-03-01"}]}}}}}  # fmt: skip
    assert public_float(cf) == PublicFloat(Decimal(0), date(2024, 6, 30)) and public_float({"facts": {}}) is None


def test_zero_float_of_a_company_listed_after_the_float_date_is_kept() -> None:
    """Review R2-F3: Figma listed in July 2025, so its first 10-K (float date 2025-06-30) reports a float of 0. It
    wasn't a reporting company on that date (first 10-Q for 2025-09-30), so it stays in."""
    from pipeline.us.universe import PublicFloat

    figma = Submissions("0001579878", "Figma, Inc.", "operating", "7372", None, "1231", ("FIG",), ("NYSE",),
                        (filing("10-Q", date(2025, 11, 5)), filing("10-K", date(2026, 2, 18))))  # fmt: skip
    got = decide(figma, BIG, RULES, TODAY, PublicFloat(Decimal(0), date(2025, 6, 30)))
    assert got.in_universe, got.reason


def test_partial_ttm_puts_a_new_registrant_in_the_universe() -> None:
    """Review F5 acceptance: GE Vernova's rows as filed by 2024-05-01 (its first 10-Q) put it in the universe."""
    import json

    from pipeline.us.companyfacts import load_facts
    from pipeline.us.quarterize import quarterize, ttm_revenue
    from pipeline.us.submissions import parse_submissions

    fix, cik, cutoff = REPO_ROOT / "fixtures" / "us", "0001996810", datetime(2024, 5, 1, tzinfo=UTC)
    doc = json.loads((fix / "companyfacts" / f"CIK{cik}.json").read_text(encoding="utf-8"))
    s = parse_submissions(json.loads((fix / "submissions" / f"CIK{cik}.json").read_text(encoding="utf-8")))
    cfg = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))["xbrl_map"]
    facts, _ = load_facts(doc, {k: v for k, v in cfg.items() if not isinstance(v, str)}, s.accepted())
    rows, _ = quarterize([f for f in facts if f.filed_at < cutoff], {f.accession: f.report_date for f in s.filings
                                                                     if f.report_date})  # fmt: skip
    ttm, partial = ttm_revenue(rows)
    assert partial and ttm is not None and ttm >= RULES.min_ttm_revenue_usd
    assert decide(s, ttm, RULES, cutoff.date()).in_universe

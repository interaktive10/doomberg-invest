"""US universe seed (BRIEF §1.3, §8 M0-05).

M0: the listed-filer seed from SEC `company_tickers_exchange.json` (cik, name, ticker, exchange), filtered to
NYSE/Nasdaq. M2: the full rules (NYSE/Nasdaq per submissions, 10-K/10-Q filer, SIC exclusions for SPACs, funds and
royalty trusts, 20-F/40-F exclusion, TTM revenue >= $50M) from submissions and fundamentals.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from pipeline.us.submissions import Submissions

SEC_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"


@dataclass(frozen=True)
class ListedFiler:
    cik: str  # zero-padded to 10 digits
    name: str
    tickers: tuple[str, ...]
    exchange: str


def parse_tickers_exchange(raw: bytes | str, exchanges: tuple[str, ...] = ("NYSE", "Nasdaq")) -> list[ListedFiler]:
    """One row per CIK listed on an allowed exchange; a CIK with several share classes keeps all its tickers."""
    doc = json.loads(raw)
    fields: list[str] = doc["fields"]
    idx = {f: fields.index(f) for f in ("cik", "name", "ticker", "exchange")}
    by_cik: dict[str, ListedFiler] = {}
    allowed = {e.lower() for e in exchanges}
    for row in doc["data"]:
        exch = row[idx["exchange"]]
        if not exch or str(exch).lower() not in allowed:
            continue
        cik = str(row[idx["cik"]]).zfill(10)
        ticker = str(row[idx["ticker"]]).upper()
        prev = by_cik.get(cik)
        if prev is None:
            by_cik[cik] = ListedFiler(cik, str(row[idx["name"]]), (ticker,), str(exch))
        elif ticker not in prev.tickers:
            by_cik[cik] = ListedFiler(cik, prev.name, (*prev.tickers, ticker), prev.exchange)
    return sorted(by_cik.values(), key=lambda f: f.cik)


def load_snapshot(path: Path) -> list[ListedFiler]:
    return parse_tickers_exchange(path.read_bytes())


# ---------------------------------------------------------------- full universe rules (BRIEF §1.3; applied in M2)


@dataclass(frozen=True)
class UniverseRules:
    exchanges: frozenset[str]
    forms_required: frozenset[str]
    spac_sic: frozenset[str]
    fund_sic_prefixes: tuple[str, ...]
    trust_sic: frozenset[str]
    foreign_forms: frozenset[str]
    min_ttm_revenue_usd: Decimal
    filing_lookback_days: int = 460  # "files 10-K/10-Q": one within ~15 months

    @classmethod
    def load(cls, root: Path) -> UniverseRules:
        cfg: dict[str, Any] = yaml.safe_load((root / "config" / "universe_us.yaml").read_text(encoding="utf-8"))
        ex = cfg["exclude"]
        return cls(
            exchanges=frozenset(e.lower() for e in cfg["exchanges"]),
            forms_required=frozenset(cfg["forms_required"]),
            spac_sic=frozenset(str(s) for s in ex["sic"]),
            fund_sic_prefixes=tuple(str(s) for s in ex["sic_prefix_funds"]),
            trust_sic=frozenset(str(s) for s in ex["sic_trusts"]),
            foreign_forms=frozenset(ex["filer_forms"]),
            min_ttm_revenue_usd=Decimal(str(cfg["min_ttm_revenue_usd"])),
        )


@dataclass(frozen=True)
class UniverseDecision:
    in_universe: bool
    reason: str | None


PREFERRED_TICKER = re.compile(r"-P[A-Z]?$")  # SEC tickers of preferred series: SCE-PB, CMS-PB; not BRK-B, BF-B


@dataclass(frozen=True)
class PublicFloat:
    value: Decimal
    as_of: date  # the measurement date (the last day of the second fiscal quarter)


def public_float(companyfacts: Mapping[str, Any]) -> PublicFloat | None:
    """dei:EntityPublicFloat from the latest 10-K (None when never reported, e.g. a new registrant)."""
    units = companyfacts.get("facts", {}).get("dei", {}).get("EntityPublicFloat", {}).get("units", {})
    rows = [r for r in units.get("USD", []) if str(r.get("form", "")).startswith("10-K") and r.get("end")]
    if not rows:
        return None
    latest = max(rows, key=lambda r: (str(r.get("filed", "")), str(r.get("end", ""))))
    return PublicFloat(Decimal(str(latest["val"])), date.fromisoformat(str(latest["end"])))


def reporting_on(subs: Submissions, day: date) -> bool:
    """Had the filer already filed a 10-K or 10-Q by `day`?"""
    return any(f.form.removesuffix("/A") in ("10-K", "10-Q") and f.filing_date <= day for f in subs.filings)


def decide(
    subs: Submissions,
    ttm_revenue: Decimal | None,
    rules: UniverseRules,
    today: date,
    pf: PublicFloat | None = None,
) -> UniverseDecision:
    """First failing rule wins, so the stored reason is the most basic one. "Common stock listed" (§1.3, review
    F6): a filer whose listed tickers are all preferred series is out, and so is one whose latest 10-K reports a
    public float of 0 while it was already a reporting company on the float date (a wholly-owned subsidiary with
    listed preferred shares or notes). An IPO or spin-off listed after the float date also reports 0 in its first
    10-K; it stays in (review R2-F3)."""
    if not any(e.lower() in rules.exchanges for e in subs.exchanges):
        return UniverseDecision(False, "not listed on NYSE/Nasdaq")
    if subs.tickers and all(PREFERRED_TICKER.search(t) for t in subs.tickers):
        return UniverseDecision(False, "no common stock listed (preferred series only)")
    if pf is not None and pf.value <= 0 and reporting_on(subs, pf.as_of):
        return UniverseDecision(False, "no public common equity (10-K public float 0)")
    sic = subs.sic or ""
    if sic in rules.spac_sic:
        return UniverseDecision(False, f"SPAC (SIC {sic})")
    if sic.startswith(rules.fund_sic_prefixes):
        return UniverseDecision(False, f"fund (SIC {sic})")
    if sic in rules.trust_sic:
        return UniverseDecision(False, f"royalty/grantor trust (SIC {sic})")
    recent = [f for f in subs.filings if (today - f.filing_date).days <= rules.filing_lookback_days]
    if any(f.form in rules.foreign_forms for f in recent):
        return UniverseDecision(False, "foreign private issuer (20-F/40-F filer)")
    if not any(f.form.removesuffix("/A") in rules.forms_required for f in recent):
        return UniverseDecision(False, "no 10-K/10-Q in the last 15 months")
    if ttm_revenue is None:
        return UniverseDecision(False, "TTM revenue unknown")
    if ttm_revenue < rules.min_ttm_revenue_usd:
        return UniverseDecision(False, f"TTM revenue {ttm_revenue:,.0f} < {rules.min_ttm_revenue_usd:,.0f}")
    return UniverseDecision(True, None)


STRUCTURAL_REASONS = (  # decide()'s reasons that describe the security rather than a moment in time
    "no common stock listed",
    "no public common equity",
    "SPAC",
    "fund",
    "royalty/grantor trust",
    "foreign private issuer",
)


def structural(sic: str | None, reason: str | None, rules: UniverseRules) -> str | None:
    """The §1.3 exclusions that don't change with time (what the security is), for replays such as the Signal Lab
    (M8 review R2-F1): SPAC, fund and royalty/grantor-trust SIC codes, preferred-only listings, no public common
    equity, foreign private issuers. The SIC rules are read from the SIC itself, since decide() stores only the first
    failing rule. The time-dependent rules (a recent 10-K/10-Q, the TTM revenue floor) are for the replay to apply
    point in time; today's listing status is not applied (it would add survivorship bias)."""
    code = sic or ""
    if code in rules.spac_sic:
        return f"SPAC (SIC {code})"
    if code.startswith(rules.fund_sic_prefixes):
        return f"fund (SIC {code})"
    if code in rules.trust_sic:
        return f"royalty/grantor trust (SIC {code})"
    return reason if reason is not None and reason.startswith(STRUCTURAL_REASONS) else None


def sector_for_sic(sic: str | None, ranges: dict[str, list[list[int]]]) -> str | None:
    """Narrowest configured SIC range containing `sic` (real estate 6500-6553 wins over financials 6000-6799)."""
    if not sic or not sic.isdigit():
        return None
    code = int(sic)
    best: tuple[int, str] | None = None
    for sector, spans in ranges.items():
        for lo, hi in spans:
            if lo <= code <= hi and (best is None or hi - lo < best[0]):
                best = (hi - lo, sector)
    return best[1] if best else None

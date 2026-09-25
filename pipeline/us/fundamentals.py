"""US fundamentals (BRIEF §4.1): SEC companyfacts + submissions -> point-in-time fundamentals_q rows.

The pure work (facts, quarterizing, sanity checks) lives in companyfacts.py and quarterize.py; this module turns the
result into typed rows and writes them. Rows keep the 60 most recent quarters (BRIEF §2.8 storage budget); the
Signal Lab builds its longer history from the raw files, not from the database.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import yaml

from pipeline.db import repo
from pipeline.db.models import FundamentalsRow
from pipeline.settings import REPO_ROOT
from pipeline.us.companyfacts import Alternative, load_facts
from pipeline.us.quarterize import Issue, QuarterRow, quarterize, ttm_revenue
from pipeline.us.submissions import Submissions

KEEP_QUARTERS = 60


def load_xbrl_map(root: Any = REPO_ROOT) -> dict[str, Sequence[Alternative]]:
    cfg = yaml.safe_load((root / "config" / "signals.yaml").read_text(encoding="utf-8"))
    return {k: v for k, v in cfg["xbrl_map"].items() if not isinstance(v, str)}


@dataclass
class CompanyResult:
    cik: str
    rows: list[QuarterRow] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    min_period: date | None = None  # quarters before this are outside the 60-quarter window

    def latest(self) -> dict[date, QuarterRow]:
        """Latest version of each quarter (rows are sorted by period_end, filed_at)."""
        return {r.period_end: r for r in self.rows}

    def ttm_revenue(self) -> Decimal | None:
        """TTM revenue as currently known; a lower bound for a company with fewer than 4 quarters (quarterize.py)."""
        return ttm_revenue(self.rows)[0]


def quarterize_company(
    companyfacts: Mapping[str, Any],
    subs: Submissions,
    xbrl_map: Mapping[str, Sequence[Alternative]],
    today: date,
    keep_quarters: int = KEEP_QUARTERS,
) -> CompanyResult:
    report_end = {f.accession: f.report_date for f in subs.filings if f.report_date}
    facts, notes = load_facts(companyfacts, xbrl_map, subs.accepted())
    rows, issues = quarterize(facts, report_end)
    cutoff = today - timedelta(days=round(keep_quarters * 91.31))
    return CompanyResult(
        cik=subs.cik,
        rows=[r for r in rows if r.period_end >= cutoff],
        issues=[i for i in issues if i.period_end >= cutoff],
        notes=notes,
        min_period=cutoff,
    )


def to_models(company_id: UUID, rows: Sequence[QuarterRow], currency: str = "USD") -> list[FundamentalsRow]:
    return [
        FundamentalsRow.model_validate(
            {
                "company_id": company_id,
                "period_end": r.period_end,
                "fiscal_label": r.fiscal_label,
                "filed_at": r.filed_at,
                "currency": currency,
                "source": "sec_xbrl",
                **r.values,
            }
        )
        for r in rows
    ]


def write_company(conn: psycopg.Connection[Any], company_id: UUID, result: CompanyResult) -> int:
    """Write the company's versions, then drop versions the current code no longer produces and quarters outside
    the window (review F10), so a code fix never leaves stale rows behind."""
    models = to_models(company_id, result.rows)
    repo.insert_fundamentals(conn, models)
    if result.min_period is not None:
        repo.prune_fundamentals(conn, company_id, [(m.period_end, m.filed_at) for m in models], result.min_period)
    return len(models)

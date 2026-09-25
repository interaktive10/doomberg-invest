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
from pipeline.us.quarterize import Issue, QuarterRow, quarterize
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

    def latest(self) -> dict[date, QuarterRow]:
        """Latest version of each quarter (rows are sorted by period_end, filed_at)."""
        return {r.period_end: r for r in self.rows}

    def ttm_revenue(self) -> Decimal | None:
        """Sum of the last 4 quarters' revenue as currently known; None if any of them is missing."""
        latest = self.latest()
        quarters = sorted(latest)[-4:]
        vals = [latest[q].values.get("revenue") for q in quarters]
        if len(vals) < 4 or any(v is None for v in vals):
            return None
        return sum((v for v in vals if v is not None), Decimal(0))


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
    models = to_models(company_id, result.rows)
    repo.insert_fundamentals(conn, models)
    return len(models)

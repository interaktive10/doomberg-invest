"""Row contracts for the tables in db/migrations (BRIEF §3, Appendix F.2). pydantic v2; Decimal for money/ratios.

Only the tables the pipeline writes or reads have a model here. Theses, kill criteria, journal and post-mortems
arrive with M6/M7. Journal and post-mortem models must never be importable from pipeline/llm (BRIEF §2.6).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Market = Literal["us", "in"]


class Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Company(Row):
    id: UUID | None = None
    market: Market
    name: str
    cik: str | None = None
    ticker: str | None = None
    isin: str | None = None
    nse_symbol: str | None = None
    bse_code: str | None = None
    sector: str | None = None
    industry: str | None = None
    sic: str | None = None
    fiscal_year_end: str | None = None
    in_universe: bool = True
    capex_desk: bool = False
    excluded_reason: str | None = None


FUNDAMENTAL_COLUMNS: tuple[str, ...] = (
    "revenue",
    "op_income",
    "net_income",
    "pretax_income",
    "tax_expense",
    "cfo",
    "capex",
    "da",
    "interest_expense",
    "total_assets",
    "cash",
    "total_debt",
    "equity",
    "receivables",
    "inventory",
    "deferred_revenue",
    "rpo",
    "diluted_shares",
    "shares_outstanding",
)


class FundamentalsRow(Row):
    """One version of one company-quarter. A restatement is a new row with a later filed_at (BRIEF §4.1.4)."""

    company_id: UUID
    period_end: date
    fiscal_label: str
    filed_at: AwareDatetime
    revenue: Decimal | None = None
    op_income: Decimal | None = None
    net_income: Decimal | None = None
    pretax_income: Decimal | None = None
    tax_expense: Decimal | None = None
    cfo: Decimal | None = None
    capex: Decimal | None = None
    da: Decimal | None = None
    interest_expense: Decimal | None = None
    total_assets: Decimal | None = None
    cash: Decimal | None = None
    total_debt: Decimal | None = None
    equity: Decimal | None = None
    receivables: Decimal | None = None
    inventory: Decimal | None = None
    deferred_revenue: Decimal | None = None
    rpo: Decimal | None = None
    diluted_shares: Decimal | None = None
    shares_outstanding: Decimal | None = None
    currency: str
    source: Literal["sec_xbrl", "nse_xbrl", "bse_xbrl", "manual"]


class OwnershipRow(Row):
    company_id: UUID
    quarter_end: date
    filed_at: AwareDatetime
    inst_holders: int | None = None
    inst_pct: Decimal | None = None
    fii_pct: Decimal | None = None
    dii_pct: Decimal | None = None
    promoter_pct: Decimal | None = None
    promoter_pledged_pct: Decimal | None = None
    source: str


InsiderKind = Literal[
    "open_market_buy", "open_market_sell", "promoter_buy", "promoter_sell", "pledge_created", "pledge_released", "other"
]


class InsiderEvent(Row):
    id: UUID | None = None
    company_id: UUID
    event_date: date
    filed_at: AwareDatetime
    person: str
    role: str | None = None
    kind: InsiderKind
    shares: Decimal | None = None
    value: Decimal | None = None
    currency: str | None = None
    planned: bool = False
    source_url: str


CorpEventKind = Literal[
    "auditor_change",
    "late_filing",
    "spinoff",
    "demerger",
    "reorganization",
    "rights_issue",
    "index_change",
    "announcement",
]


class CorpEvent(Row):
    id: UUID | None = None
    company_id: UUID
    event_date: date
    filed_at: AwareDatetime
    kind: CorpEventKind
    detail: dict[str, Any] = Field(default_factory=dict)
    source_url: str


class FilingRow(Row):
    """Appendix F.2 `filings`: a filing queued for text extraction (M5)."""

    company_id: UUID
    accession_no: str
    form_type: str
    items: list[str] = Field(default_factory=list)
    filed_at: AwareDatetime
    accepted_at: AwareDatetime | None = None
    period_of_report: date | None = None
    primary_doc_url: str
    index_url: str
    status: Literal["new", "fetched", "normalized", "extracted", "verified", "skipped", "failed"] = "new"


class PriceW(Row):
    company_id: UUID
    week_end: date
    close: Decimal
    adj_close: Decimal | None = None
    volume: Decimal | None = None
    source: str


class BenchmarkW(Row):
    symbol: str
    week_end: date
    close: Decimal


class SignalValue(Row):
    company_id: UUID
    week_end: date
    signal_id: str
    fired: bool
    strength: Decimal = Field(ge=0, le=1)
    inputs: dict[str, Any]


class RedflagValue(Row):
    company_id: UUID
    week_end: date
    flag_id: str
    hard: bool
    inputs: dict[str, Any]


class ContextValue(Row):
    company_id: UUID
    week_end: date
    metric_id: str
    value: Decimal | None = None
    pct: Decimal | None = None
    inputs: dict[str, Any]


class Score(Row):
    company_id: UUID
    week_end: date
    evidence: Decimal
    gap: Decimal | None = None
    families: list[str]
    bucket: Literal["candidate", "priced_in", "early", "excluded", "none"]
    weights_version: str


class WeightsVersion(Row):
    version: str
    weights: dict[str, Any]
    reason: str
    approved_by: str | None = None
    approved_at: AwareDatetime | None = None


class LabResult(Row):
    signal_id: str
    market: str
    horizon_m: int
    period: Literal["in_sample", "out_of_sample"]
    n: int
    excess_mean: Decimal | None = None
    excess_median: Decimal | None = None
    hit_rate: Decimal | None = None
    p10: Decimal | None = None
    t_nw: Decimal | None = None
    notes: str | None = None


class SourceHealth(Row):
    source: str
    last_success: datetime | None = None
    last_error: str | None = None
    stale: bool = False


class LlmCall(Row):
    run_id: UUID | None = None
    prompt_id: str
    provider: str
    model: str
    ok: bool
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    error: str | None = None

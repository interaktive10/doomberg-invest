"""The screener API (BRIEF §8 M4-05): a typed filter spec over the latest scored week.

The database does the filtering: `screen(spec jsonb)` over `screener_v` (db/migrations/0007). The web app's Candidates
screen calls the same function as an RPC with service_role, sending part of this spec (web/lib/screener.ts, a plain
TypeScript type: one bucket, market, families and a limit); the Screener UI that built full specs and saved them in
`saved_screens` was deleted in overhaul PR 4 (docs/SPEC_ISSUES.md 52). Every field is optional; metric filters use
the keys of company_metrics."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

METRICS = frozenset({
    "revenue_ttm", "revenue_yoy", "opm", "roic", "fcf_ttm", "ccr", "nd_to_ebitda", "share_change_yoy", "market_cap",
    "ev", "return_52w",
})  # fmt: skip
Bucket = Literal["candidate", "priced_in", "early", "watch", "excluded", "none"]
Family = Literal["fundamentals", "behavior", "text", "structural", "capex", "cycle"]
SignalId = Literal["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12"]


class MetricFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metric: str
    op: Literal[">=", "<=", ">", "<"]
    value: Decimal

    @field_validator("metric")
    @classmethod
    def known_metric(cls, v: str) -> str:
        if v not in METRICS:
            raise ValueError(f"unknown metric {v!r}; one of {sorted(METRICS)}")
        return v


class ScreenSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    market: Literal["us", "in"] | None = None
    capex_desk: bool | None = None
    sector: str | None = None
    buckets: list[Bucket] | None = None
    min_evidence: Decimal | None = Field(default=None, ge=0, le=100)
    min_gap: Decimal | None = Field(default=None, ge=0, le=100)
    signals_any: list[SignalId] | None = None
    families_all: list[Family] | None = None
    exclude_hard_flags: bool = False
    metrics: list[MetricFilter] = Field(default_factory=list)
    limit: int = Field(default=500, ge=1, le=2000)

    def as_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def run_screen(conn: psycopg.Connection[Any], spec: ScreenSpec) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(b"select * from screen(%s)", (Jsonb(spec.as_json()),))
        return list(cur.fetchall())

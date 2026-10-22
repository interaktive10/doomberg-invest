"""Evidence packs (BRIEF §4.9): everything a thesis card may say about one company in one week, as JSON, public data
only, every item under a stable id.

- identifiers, the week's scores (Evidence, Gap, bucket, families);
- the last 12 quarters of key metrics (`m:<metric>:<period_end>`), as the week's point-in-time reader sees them;
- the week's fired signals and red flags with their inputs (`s:S1`, `s:R2`), the context metrics C1-C3 with their
  inputs, reverse-DCF assumptions included (`c:C2`), Evidence and Gap (`c:evidence`, `c:gap`);
- at most 20 verified text facts with quote, URL and fact id (`f:<uuid>`), the newest first;
- ownership by quarter (`m:<field>:<quarter_end>`) and insider events of the last year (`m:insider:<uuid>`);
- the Capex Desk's counterparty links (each with the fact that made it) and confirmed categories;
- candidate kill-criteria metrics, the current value of each (`m:<metric>`, e.g. `m:revenue_ttm_yoy`); a kill
  criterion names one of these and kill_criteria.py recomputes it from new data with the same code;
- the next expected filing window (a kill criterion's check_after must fall after it).

Public data only: filings, exchange data and values computed from them (the thesis module's other tables never
come in; the guard's privacy_rule covers this file). `CardInput` (P-04) and `ClaimInput` (P-05) are the router
inputs built from a pack.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar, Literal
from uuid import UUID

import psycopg
from pydantic import BaseModel, ConfigDict

from pipeline.db import thesis_repo
from pipeline.db.models import Company, InsiderEvent, OwnershipRow
from pipeline.db.pit import as_of
from pipeline.lab.prices import add_months, month_end
from pipeline.llm.prompt import PromptInput, obj, template
from pipeline.signals.series import Series, growth

PACK_VERSION = 1
QUARTERS = 12
MAX_FACTS = 20
MAX_INSIDERS = 20
OWNERSHIP_QUARTERS = 8
INSIDER_DAYS = 365
MONEY = ("revenue", "op_income", "net_income", "cfo", "capex", "fcf", "rpo", "total_debt", "cash", "equity")
SHARES = ("diluted_shares", "shares_outstanding")
OWNERSHIP = ("inst_holders", "fii_pct", "dii_pct", "promoter_pct", "promoter_pledged_pct")
ID = re.compile(r"^(?:m:[a-z0-9_]+(?::[A-Za-z0-9_.\-]+)?|f:[0-9a-f\-]{36}|s:[A-Z][0-9]{1,2}|c:[A-Za-z0-9_]+)$")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Identifiers(Model):
    company_id: UUID
    key: str  # data/thesis_cards/<week>/<key>.json
    name: str
    market: Literal["us", "in"]
    ticker: str | None = None
    nse_symbol: str | None = None
    cik: str | None = None
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    capex_desk: bool = False
    fiscal_year_end: str | None = None


class Metric(Model):
    id: str
    name: str
    period_end: date | None = None
    value: Decimal | None
    unit: str  # a currency code (usd, inr), "shares", "count", "ratio" (0.14 = 14%) or "percent" (12.5 = 12.5%)
    source: str


class SignalItem(Model):
    id: str
    kind: Literal["signal", "red_flag"]
    fired: bool
    strength: Decimal | None = None
    hard: bool | None = None
    status: str | None = None  # red flags: fired / unknown
    inputs: dict[str, Any]


class ContextItem(Model):
    id: str
    value: Decimal | None = None
    pct: Decimal | None = None
    inputs: dict[str, Any]


class FactItem(Model):
    id: str
    fact_type: str
    subject: str
    subject_key: str
    value: Decimal | None = None
    value_low: Decimal | None = None
    value_high: Decimal | None = None
    unit: str
    currency: str | None = None
    period_label: str | None = None
    period_end: date | None = None
    as_of: date
    counterparty: str | None = None
    quote: str
    url: str
    document_kind: str
    published_at: datetime


class InsiderItem(Model):
    id: str
    event_date: date
    filed_at: datetime
    person: str
    role: str | None = None
    kind: str
    shares: Decimal | None = None
    value: Decimal | None = None
    currency: str | None = None
    planned: bool
    amends: date | None = None


class LinkItem(Model):
    entity: str
    entity_kind: str
    relation: str
    fact_id: str


class KillMetric(Model):
    id: str
    description: str
    value: Decimal | None
    unit: str


class FilingWindow(Model):
    period_end: date
    form: str
    opens: date
    closes: date


class EvidencePack(Model):
    version: int
    week: str  # ISO week, e.g. 2026-W38
    week_end: date
    company: Identifiers
    bucket: str | None
    families: list[str]
    metrics: list[Metric]
    signals: list[SignalItem]
    context: list[ContextItem]
    facts: list[FactItem]
    ownership: list[Metric]
    insiders: list[InsiderItem]
    capex_categories: list[str]
    capex_links: list[LinkItem]
    kill_metrics: list[KillMetric]
    next_filing: FilingWindow | None

    def ids(self) -> list[str]:
        """Every citable id, in pack order (one generator per item type: mypy joins a mixed tuple to Model)."""
        return [*(x.id for x in self.metrics), *(x.id for x in self.signals), *(x.id for x in self.context),
                *(x.id for x in self.facts), *(x.id for x in self.ownership), *(x.id for x in self.insiders),
                *(x.id for x in self.kill_metrics)]  # fmt: skip


def week_label(week_end: date) -> str:
    iso = week_end.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def company_key(c: Company) -> str:
    code = c.ticker if c.market == "us" else c.nse_symbol
    raw = code or re.sub(r"[^a-z0-9]+", "-", c.name.lower()).strip("-")
    return f"{c.market}-{re.sub(r'[^a-z0-9.-]+', '-', raw.lower())}"


# ---------------------------------------------------------------- kill-criteria metrics

KillFn = Callable[["KillInputs"], Decimal | None]


@dataclass(frozen=True)
class KillInputs:
    series: Series
    holdings: Sequence[OwnershipRow]
    signal_strength: Mapping[str, Decimal]  # the latest scored week's signals (0 when quiet)
    evidence: Decimal | None


def _latest_holding(k: KillInputs, field: str) -> Decimal | None:
    rows = sorted((h for h in k.holdings if getattr(h, field) is not None), key=lambda h: h.quarter_end)
    v = getattr(rows[-1], field) if rows else None
    return None if v is None else Decimal(v)


def _fii_dii(k: KillInputs) -> Decimal | None:
    rows = sorted((h for h in k.holdings if h.fii_pct is not None and h.dii_pct is not None),
                  key=lambda h: h.quarter_end)  # fmt: skip
    return None if not rows else (rows[-1].fii_pct or Decimal(0)) + (rows[-1].dii_pct or Decimal(0))


def _yoy_point(s: Series, col: str) -> Decimal | None:
    return growth(s.point(col, 0), s.point(col, 4)) if s.year_back_ok(0) else None


def _shares_yoy(s: Series) -> Decimal | None:
    (now, _), (then, _) = s.shares(0), s.shares(4)
    return growth(now, then) if s.year_back_ok(0) else None


KILL_METRICS: dict[str, tuple[str, str, KillFn]] = {
    "revenue_ttm": ("trailing-twelve-month revenue", "money", lambda k: k.series.ttm("revenue", 0)),
    "revenue_ttm_yoy": ("TTM revenue vs the TTM a year earlier (0.10 = +10%)", "ratio",
                        lambda k: k.series.ttm_yoy("revenue", 0)),
    "revenue_q_yoy": ("latest quarter's revenue vs the same quarter a year earlier", "ratio",
                      lambda k: k.series.quarterly_yoy("revenue", 0)),
    "op_margin_ttm": ("TTM operating income / TTM revenue", "ratio", lambda k: k.series.opm(0)),
    "roic": ("TTM NOPAT / mean invested capital (BRIEF §4.6)", "ratio", lambda k: k.series.roic(0)),
    "fcf_ttm": ("TTM operating cash flow minus capex", "money", lambda k: k.series.fcf(0)),
    "net_debt": ("total debt minus cash at the latest quarter end", "money", lambda k: k.series.net_debt(0)),
    "rpo": ("remaining performance obligations at the latest quarter end", "money",
            lambda k: k.series.value("rpo", 0)),
    "rpo_yoy": ("RPO vs a year earlier", "ratio", lambda k: _yoy_point(k.series, "rpo")),
    "shares_yoy": ("share count vs a year earlier (dilution when > 0)", "ratio", lambda k: _shares_yoy(k.series)),
    "inst_holders": ("13F institutional holders, latest quarter (US)", "count",
                     lambda k: _latest_holding(k, "inst_holders")),
    "fii_dii_pct": ("FII + DII holding %, latest pattern (India)", "percent", _fii_dii),
    "promoter_pct": ("promoter holding %, latest pattern (India)", "percent",
                     lambda k: _latest_holding(k, "promoter_pct")),
    "promoter_pledged_pct": ("pledged shares as % of the promoter holding (India)", "percent",
                             lambda k: _latest_holding(k, "promoter_pledged_pct")),
    "evidence": ("Evidence score, latest scored week (0-100)", "score", lambda k: k.evidence),
}  # fmt: skip
SIGNAL_METRIC = re.compile(r"^signal:(S\d{1,2})$")  # m:signal:S1 = S1's strength in the latest scored week


def kill_value(metric: str, k: KillInputs) -> Decimal | None:
    """The current value of a kill-criteria metric id (without its `m:` prefix)."""
    if metric in KILL_METRICS:
        return KILL_METRICS[metric][2](k)
    m = SIGNAL_METRIC.match(metric)
    if m:
        return k.signal_strength.get(m.group(1), Decimal(0))
    raise KeyError(metric)


def is_kill_metric(metric_id: str) -> bool:
    name = metric_id.removeprefix("m:")
    return metric_id.startswith("m:") and (name in KILL_METRICS or SIGNAL_METRIC.match(name) is not None)


def kill_inputs(conn: psycopg.Connection[Any], company: Company, week: date) -> KillInputs:
    """Kill-metric inputs as of `week` (the point-in-time readers; the latest scored week's signals)."""
    assert company.id is not None
    snap = as_of(week)
    series = Series.from_rows(snap.fundamentals(conn, [company.id]), company.market)
    _, signals = thesis_repo.latest_signals(conn, company.id, week)
    score = thesis_repo.week_score(conn, company.id, week)
    strengths = {s.signal_id: s.strength for s in signals}
    evidence = None if score is None else score.evidence
    return KillInputs(series, snap.ownership(conn, [company.id]), strengths, evidence)


# ---------------------------------------------------------------- the next filing window


def next_filing(market: str, fye: str | None, latest_end: date | None, week: date) -> FilingWindow | None:
    """The next report after the latest known quarter: US 10-Q within 45 days of the quarter end, 10-K within 90;
    India results within 45 days (60 for the fiscal year's last quarter). A window that already closed moves on a
    quarter (a late filer)."""
    if latest_end is None:
        return None
    fy_month = int(fye[:2]) if fye and len(fye) == 4 and fye.isdigit() else (3 if market == "in" else 12)
    end = latest_end
    for _ in range(8):
        end = month_end(add_months(end, 3))
        annual = end.month == fy_month
        days = (90 if annual else 45) if market == "us" else (60 if annual else 45)
        form = ("10-K" if annual else "10-Q") if market == "us" else ("annual results" if annual else "results")
        window = FilingWindow(
            period_end=end, form=form, opens=end + timedelta(days=1), closes=end + timedelta(days=days)
        )
        if window.closes >= week:
            return window
    return None


# ---------------------------------------------------------------- building a pack


def _num(x: Any) -> Decimal | None:
    return None if x is None else x if isinstance(x, Decimal) else Decimal(str(x))


def _metrics(series: Series, currency: str) -> list[Metric]:
    out = []
    for q in series.quarters[-QUARTERS:]:
        values = dict(q.values)
        cfo, capex = values.get("cfo"), values.get("capex")
        values["fcf"] = None if cfo is None or capex is None else cfo - capex
        for col in (*MONEY, *SHARES):
            v = values.get(col)
            if v is not None:
                unit = currency if col in MONEY else "shares"
                out.append(Metric(id=f"m:{col}:{q.end.isoformat()}", name=col, period_end=q.end, value=v, unit=unit,
                                  source="computed (cfo - capex)" if col == "fcf" else "fundamentals"))  # fmt: skip
    return out


def _ownership(rows: Iterable[OwnershipRow]) -> list[Metric]:
    out = []
    for h in sorted(rows, key=lambda r: r.quarter_end)[-OWNERSHIP_QUARTERS:]:
        for field in OWNERSHIP:
            v = getattr(h, field)
            if v is not None:
                unit = "count" if field == "inst_holders" else "percent"
                out.append(Metric(id=f"m:{field}:{h.quarter_end.isoformat()}", name=field, period_end=h.quarter_end,
                                  value=Decimal(v), unit=unit, source=h.source))  # fmt: skip
    return out


def _insiders(rows: Iterable[InsiderEvent], week: date) -> list[InsiderItem]:
    since = week - timedelta(days=INSIDER_DAYS)
    recent = sorted((e for e in rows if e.event_date >= since and e.id is not None),
                    key=lambda e: (e.event_date, e.filed_at), reverse=True)[:MAX_INSIDERS]  # fmt: skip
    return [InsiderItem(id=f"m:insider:{e.id}", event_date=e.event_date, filed_at=e.filed_at, person=e.person,
                        role=e.role, kind=e.kind, shares=e.shares, value=e.value, currency=e.currency,
                        planned=e.planned, amends=e.amends) for e in recent]  # fmt: skip


def build(conn: psycopg.Connection[Any], company: Company, week: date) -> EvidencePack:
    """The pack for `company` as of week `week` (its scores, signals and context rows must exist for that week)."""
    assert company.id is not None
    cid = company.id
    snap = as_of(week)
    rows = snap.fundamentals(conn, [cid])
    currency = (rows[-1].currency or "USD").lower() if rows else ("inr" if company.market == "in" else "usd")
    series = Series.from_rows(rows, company.market)
    holdings = snap.ownership(conn, [cid])
    score = thesis_repo.week_score(conn, cid, week)
    signals = thesis_repo.week_signals(conn, cid, week)
    flags = thesis_repo.week_flags(conn, cid, week)
    context = thesis_repo.week_context(conn, cid, week)
    facts = thesis_repo.pack_facts(conn, cid, snap.cutoff, MAX_FACTS)
    links = thesis_repo.pack_links(conn, cid, snap.cutoff)
    kin = KillInputs(series, holdings, {s.signal_id: s.strength for s in signals},
                     None if score is None else score.evidence)  # fmt: skip
    kills = []
    for name, (desc, unit, fn) in KILL_METRICS.items():
        kills.append(
            KillMetric(id=f"m:{name}", description=desc, value=fn(kin), unit=currency if unit == "money" else unit)
        )
    kills += [KillMetric(id=f"m:signal:{s.signal_id}", description=f"{s.signal_id} strength, latest scored week (0-1)",
                         value=s.strength, unit="score") for s in signals if s.fired]  # fmt: skip
    ctx = [ContextItem(id=f"c:{c.metric_id}", value=c.value, pct=c.pct, inputs=c.inputs) for c in context]
    if score is not None:
        ctx += [ContextItem(id="c:evidence", value=score.evidence, inputs={"families": list(score.families)}),
                ContextItem(id="c:gap", value=score.gap, inputs={})]  # fmt: skip
    return EvidencePack(
        version=PACK_VERSION,
        week=week_label(week),
        week_end=week,
        company=Identifiers(
            company_id=cid,
            key=company_key(company),
            name=company.name,
            market=company.market,
            ticker=company.ticker,
            nse_symbol=company.nse_symbol,
            cik=company.cik,
            isin=company.isin,
            sector=company.sector,
            industry=company.industry,
            capex_desk=bool(company.capex_desk),
            fiscal_year_end=company.fiscal_year_end,
        ),  # fmt: skip
        bucket=None if score is None else score.bucket,
        families=[] if score is None else sorted(score.families),
        metrics=_metrics(series, currency),
        signals=[
            SignalItem(id=f"s:{s.signal_id}", kind="signal", fired=True, strength=s.strength, inputs=s.inputs)
            for s in signals
            if s.fired
        ]  # fmt: skip
        + [
            SignalItem(
                id=f"s:{f.flag_id}",
                kind="red_flag",
                fired=f.inputs.get("status") == "fired",
                hard=f.hard,
                status=str(f.inputs.get("status")),
                inputs={k: v for k, v in f.inputs.items() if k != "status"},
            )
            for f in flags
        ],  # fmt: skip
        context=ctx,
        facts=[
            FactItem(
                id=f"f:{r['id']}",
                fact_type=r["fact_type"],
                subject=r["subject"],
                subject_key=r["subject_key"],
                value=_num(r["value_num"]),
                value_low=_num(r["value_low"]),
                value_high=_num(r["value_high"]),
                unit=r["unit"],
                currency=r["currency"],
                period_label=r["period_label"],
                period_end=r["period_end"],
                as_of=r["as_of"],
                counterparty=r["counterparty"],
                quote=r["quote"],
                url=r["url"],
                document_kind=r["kind"],
                published_at=r["published_at"],
            )
            for r in facts
        ],  # fmt: skip
        ownership=_ownership(holdings),
        insiders=_insiders(snap.insider_events(conn, [cid], since=week - timedelta(days=INSIDER_DAYS)), week),
        capex_categories=thesis_repo.confirmed_categories(conn, cid),
        capex_links=[
            LinkItem(
                entity=r["entity"], entity_kind=r["entity_kind"], relation=r["relation"], fact_id=f"f:{r['fact_id']}"
            )
            for r in links
        ],  # fmt: skip
        kill_metrics=kills,
        next_filing=next_filing(company.market, company.fiscal_year_end, series.latest_end, week),
    )


def to_json(pack: EvidencePack) -> dict[str, Any]:
    """The pack as stored and sent: JSON-mode dump (Decimals as strings, dates ISO)."""
    doc: dict[str, Any] = pack.model_dump(mode="json")
    return doc


# ---------------------------------------------------------------- numbers under each id (for validate.py)


def _numbers(x: Any) -> list[Decimal]:
    if isinstance(x, bool) or x is None:
        return []
    if isinstance(x, (int, float, Decimal)):
        return [Decimal(str(x))]
    if isinstance(x, str):
        try:
            return [Decimal(x)] if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", x.strip()) else []
        except ArithmeticError:
            return []
    if isinstance(x, Mapping):
        return [n for v in x.values() for n in _numbers(v)]
    if isinstance(x, (list, tuple)):
        return [n for v in x for n in _numbers(v)]
    return []


VALUE_FIELDS = ("value", "value_low", "value_high", "strength", "pct", "shares", "inputs")


def values_by_id(pack: Mapping[str, Any]) -> dict[str, list[Decimal]]:
    """Every number a card may cite, by pack id (from the JSON form of the pack)."""
    out: dict[str, list[Decimal]] = {}
    for section in ("metrics", "signals", "context", "facts", "ownership", "insiders", "kill_metrics"):
        for item in pack.get(section) or []:
            out[str(item["id"])] = [n for f in VALUE_FIELDS for n in _numbers(item.get(f))]
    return out


def units_by_id(pack: Mapping[str, Any]) -> dict[str, str]:
    return {str(i["id"]): str(i.get("unit") or "") for s in ("metrics", "facts", "ownership", "kill_metrics")
            for i in pack.get(s) or []}  # fmt: skip


# ---------------------------------------------------------------- router inputs (public data)


CARD_SCHEMA = obj({
    "summary": {"type": "string"},
    "facts": {"type": "array", "items": obj({"text": {"type": "string"},
                                              "cites": {"type": "array", "items": {"type": "string"}}})},
    "why_mispriced": {"type": "array", "items": obj({"text": {"type": "string"},
                                                      "cites": {"type": "array", "items": {"type": "string"}}})},
    "inferences": {"type": "array", "items": {"type": "string"}},
    "assumptions": {"type": "array", "items": {"type": "string"}},
    "risks": {"type": "array", "items": obj({"text": {"type": "string"},
                                              "cites": {"type": "array", "items": {"type": "string"}}})},
    "kill_criteria": {"type": "array", "items": obj({
        "metric_id": {"type": "string"},
        "operator": {"type": "string", "enum": ["<", "<=", ">", ">=", "==", "changes"]},
        "threshold": {"type": "number", "nullable": True},
        "check_after": {"type": "string"},
        "why": {"type": "string"}})},
    "read_next": {"type": "array", "items": obj({"title": {"type": "string"}, "url": {"type": "string"}})},
})  # fmt: skip


@dataclass(frozen=True)
class CardInput(PromptInput):
    """P-04 (the fallback writer): the evidence pack itself, validated (BRIEF §2.6: the router takes EvidencePack
    types; M6 review R1-F4), sent as its JSON."""

    prompt_id: ClassVar[str] = "P-04"
    pack: EvidencePack

    def variables(self) -> dict[str, str]:
        return {"pack_json": json.dumps(to_json(self.pack), indent=1, ensure_ascii=False)}

    def schema(self) -> dict[str, Any]:
        return CARD_SCHEMA


SUPPORT_SCHEMA = obj({"supported": {"type": "boolean"},
                      "unsupported_parts": {"type": "array", "items": {"type": "string"}},
                      "reason": {"type": "string"}})  # fmt: skip


@dataclass(frozen=True)
class ClaimInput(PromptInput):
    """P-05: one card sentence, the quotes of the facts it cites and the cited values (validate.py)."""

    prompt_id: ClassVar[str] = "P-05"
    sentence: str
    quotes: tuple[str, ...]
    computed: tuple[str, ...]

    def variables(self) -> dict[str, str]:
        return {"sentence": self.sentence, "quotes": json.dumps(list(self.quotes), ensure_ascii=False),
                "computed": json.dumps(list(self.computed), ensure_ascii=False)}  # fmt: skip

    def schema(self) -> dict[str, Any]:
        return SUPPORT_SCHEMA


def p04_system() -> str:
    return template("P-04", "system")

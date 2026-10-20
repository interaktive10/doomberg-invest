"""The weekly Capex Desk run (BRIEF §4.11; no weekly.yml job since overhaul PR 1: without EIA, S11 can't fire).
`python -m pipeline.capex.run --stage index|brief [--week D]`.

index (before scoring):
1. EIA planned generator additions (free key, EIA_API_KEY) -> capex_inputs, monthly.
2. Demand inputs at every week of the history, point in time (facts published by then), YoY, z, and the index per
   category -> capex_inputs (this week's levels) and capex_index.
3. Memberships: US proposals from the industry map (capex desk by seed group; other ledger companies by SIC); India
   P-06 on each scope company's announcements and annual-report excerpts (grounded quotes; every 90 days; at most
   P06_PER_RUN a week). Proposals wait for Manzoor's confirmation; an export share or overseas order book becomes an
   `export_exposure` fact through Verify-1.
brief (after scoring): the markdown Capex brief for the digest -> capex_briefs.

`load_views` gives the weekly scoring run S11's CapexView per company (confirmed memberships only).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg
import yaml

from pipeline.capex import annual_report, eia, inputs, membership
from pipeline.capex.brief import IndexMove, NewFact, render
from pipeline.capex.desk import anchors, config
from pipeline.capex.index import Panel, categories, input_stat
from pipeline.db import facts_repo, repo
from pipeline.db.models import Company
from pipeline.db.pit import as_of, cutoff_for
from pipeline.facts.chunk import Chunk, score
from pipeline.facts.extract import Proposed
from pipeline.facts.fetch import store_raw
from pipeline.facts.pdf_text import page_texts
from pipeline.facts.process import normalize
from pipeline.facts.verify1 import Candidate, DocContext, verify
from pipeline.llm.router import Deferred, Router
from pipeline.net.http import HttpClient
from pipeline.net.nse import NseBlocked, NseClient
from pipeline.settings import REPO_ROOT, Settings

P06_PER_RUN = 20
P06_REFRESH_DAYS = 90
EIA_YEARS = 5
ANNOUNCEMENT_DAYS = 365


def seed_groups(root: Path = REPO_ROOT) -> dict[str, str]:
    """US ticker -> its Appendix H group in config/capex_seed.yaml."""
    doc = yaml.safe_load((root / "config" / "capex_seed.yaml").read_text(encoding="utf-8"))
    return {str(t).upper(): g for g, tickers in (doc.get("us") or {}).items() for t in tickers}


@dataclass
class CapexStats:
    week: str
    eia_months: int = 0
    inputs: dict[str, dict[str, str | None]] = field(default_factory=dict)
    rising: list[str] = field(default_factory=list)
    proposed_us: int = 0
    proposed_in: int = 0
    p06_companies: int = 0
    p06_dropped: int = 0
    p06_deferred: int = 0
    export_facts: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- the index


def levels(facts: Sequence[inputs.FactLike], anchor_ids: Mapping[UUID, str], eia_series: Sequence[tuple[date, Decimal]],
           cfg: Mapping[str, Any]) -> dict[str, Callable[[date], Panel | Decimal | None]]:  # fmt: skip
    age = int(cfg["index"]["fact_max_age_days"])
    out: dict[str, Callable[[date], Panel | Decimal | None]] = {
        "hyperscaler_capex_guidance": lambda d: inputs.guidance(facts, anchor_ids, d, age),
        "utility_large_load_gw": lambda d: inputs.large_load(facts, d, age),
        "eia_planned_additions_mw": lambda d: inputs.series_at(eia_series, d),
    }
    for input_id, equipment in cfg["lead_time_equipment"].items():
        out[input_id] = _lead_time(facts, str(equipment), age)
    return out


def _lead_time(facts: Sequence[inputs.FactLike], equipment: str, age: int) -> Callable[[date], Decimal | None]:
    return lambda d: inputs.lead_time(facts, equipment, d, age)


def build_index(conn: psycopg.Connection[Any], week: date, companies: Sequence[Company], cfg: Mapping[str, Any],
                stats: CapexStats) -> None:  # fmt: skip
    ic = cfg["index"]
    span = timedelta(weeks=int(ic["history_weeks"]) + 53) + timedelta(days=int(ic["fact_max_age_days"]))
    facts = as_of(week).facts(conn, None, since=week - span)
    eia_series = facts_repo.capex_input_history(conn, "eia_planned_additions_mw", week - span, week)
    stat = {k: input_stat(k, level, week, int(ic["history_weeks"]), int(ic["min_history"]), float(ic["min_spread"]))
            for k, level in levels(facts, anchors(companies, cfg), eia_series, cfg).items()}  # fmt: skip
    facts_repo.upsert_capex_inputs(conn, week, {
        k: (s.level, {"yoy": None if s.yoy is None else str(s.yoy), "z": None if s.z is None else str(s.z),
                      "history": s.history})
        for k, s in stat.items() if k != "eia_planned_additions_mw"})  # fmt: skip
    rows = categories(stat, cfg)
    facts_repo.upsert_capex_index(conn, week, [asdict(r) for r in rows])
    stats.inputs = {k: {"level": None if s.level is None else str(s.level), "z": None if s.z is None else str(s.z)}
                    for k, s in stat.items()}  # fmt: skip
    stats.rising = [r.category for r in rows if r.direction == "rising"]


def ingest_eia(conn: psycopg.Connection[Any], http: HttpClient, key: str | None, week: date, stats: CapexStats) -> None:
    if not key:
        stats.errors.append("EIA_API_KEY not set: the EIA input is missing (BRIEF §0.5)")
        return
    try:
        series = eia.planned_additions(http, key, week - timedelta(days=365 * EIA_YEARS), week)
    except eia.EiaError as e:
        stats.errors.append(str(e))
        repo.mark_source_error(conn, "eia", str(e), stale=False)
        return
    for month, mw in series:  # filed under the month it is published in, so a re-run of a past week reads what was out
        facts_repo.upsert_capex_inputs(conn, eia.available(month), {
            "eia_planned_additions_mw": (mw, {"source": "EIA-860M planned", "month": f"{month:%Y-%m}"})})  # fmt: skip
    stats.eia_months = len(series)
    repo.mark_source_success(conn, "eia")


# ---------------------------------------------------------------- memberships


def propose_us(conn: psycopg.Connection[Any], companies: Sequence[Company], cfg: Mapping[str, Any],
               ledger: set[UUID], stats: CapexStats) -> None:  # fmt: skip
    groups = seed_groups()
    for c in companies:
        if c.market != "us" or c.id is None or not (c.capex_desk or c.id in ledger):
            continue
        group = groups.get((c.ticker or "").upper()) if c.capex_desk else None
        cats, why = membership.us_categories(group, c.sic, cfg)
        for cat in cats:
            stats.proposed_us += facts_repo.propose_membership(conn, c.id, cat, "industry_map", why)


def india_text(conn: psycopg.Connection[Any], nse: NseClient | None, c: Company, week: date,
               stats: CapexStats) -> list[tuple[str, str]]:  # fmt: skip
    assert c.id is not None
    parts = []
    for e in as_of(week).corp_events(conn, [c.id], since=week - timedelta(days=ANNOUNCEMENT_DAYS)):
        cat, body = str(e.detail.get("category") or "").strip(), str(e.detail.get("text") or "").strip()
        text = f"{cat}. {body}" if cat and body else cat or body
        if e.kind == "announcement" and score(text) >= 1:
            parts.append((f"Announcement {e.event_date:%Y-%m-%d}", text))
    if nse is not None and c.nse_symbol:
        try:
            rep = annual_report.latest(nse.api(annual_report.listing_path(c.nse_symbol)))
            if rep is not None and rep.published <= cutoff_for(week):
                pdf = nse.get(rep.url)
                if len(pdf) <= annual_report.MAX_PDF_BYTES:
                    parts += annual_report.excerpts(page_texts(pdf), rep.label)
        except (NseBlocked, httpx.HTTPError, ValueError, KeyError) as e:
            stats.errors.append(f"annual report {c.nse_symbol}: {type(e).__name__}"[:200])
    return parts


def cross_border(
    conn: psycopg.Connection[Any],
    router: Router,
    nse: NseClient | None,
    companies: Sequence[Company],
    scope: set[UUID],
    week: date,
    cfg: Mapping[str, Any],
    raw_root: Path,
    stats: CapexStats,
) -> None:
    recent = facts_repo.p06_recent(conn, week - timedelta(days=P06_REFRESH_DAYS))
    cats = tuple(cfg["categories"])
    todo = [c for c in companies if c.market == "in" and c.id in scope and c.id not in recent][:P06_PER_RUN]
    for c in todo:
        assert c.id is not None
        if router.exhausted("P-06"):
            stats.p06_deferred += 1
            continue
        raw = membership.profile_text(india_text(conn, nse, c, week, stats))
        if not raw:
            continue
        url = f"nse-profile:{c.nse_symbol}:{week:%Y-%m-%d}"
        full = normalize(url, raw.encode()).text  # the canonical text every offset refers to (Appendix F.3)
        text = full[: membership.MAX_TEXT_CHARS]  # what P-06 sees, and all a quote is grounded in (M5 review R1-F3)
        answer = router.call(membership.CrossBorderInput(c.name, c.nse_symbol or "", cats, text))
        if isinstance(answer, Deferred):
            stats.p06_deferred += 1
            continue
        stats.p06_companies += 1
        r = membership.parse(answer.content, text, cats)
        stats.p06_dropped += len(r.dropped)
        path, digest = store_raw(raw_root, c.nse_symbol or str(c.id), "profile", f"{week:%Y%m%d}.txt", raw.encode())
        doc_id = facts_repo.upsert_document(
            conn, company_id=c.id, kind="other", url=url, title="P-06 text: announcements and annual-report excerpts",
            published_at=datetime.combine(week, datetime.min.time(), UTC), sha256=digest, raw_path=str(path),
            text_chars=len(full), status="extracted",
        )  # fmt: skip
        for g in r.categories:
            stats.proposed_in += facts_repo.propose_membership(
                conn, c.id, g.category, "p06", membership.evidence(g), g.quote, doc_id, (g.char_start, g.char_end),
                g.confidence)  # fmt: skip
        if r.export is not None:
            stats.export_facts += export_fact(conn, c, doc_id, text, r.export, week, answer.provider, answer.model)
        facts_repo.set_document_status(conn, doc_id, "extracted")


def export_fact(conn: psycopg.Connection[Any], c: Company, doc_id: UUID, text: str, e: membership.Export, week: date,
                provider: str, model: str) -> int:  # fmt: skip
    """P-06's export exposure as an `export_exposure` fact, through Verify-1 like any P-01 fact."""
    assert c.id is not None
    share = e.share_pct is not None
    p = Proposed(fact_type="export_exposure", subject="export share of revenue" if share else "overseas order book",
                 subject_key="export_exposure:share_pct" if share else "export_exposure:overseas_order_book",
                 value=e.share_pct, value_low=None, value_high=None, unit="percent" if share else "other",
                 currency=None, scale_word=None, period_label=None, as_of=None, counterparty=None, location=None,
                 withdrawn=False, quote=e.quote, confidence=Decimal("0.80"))  # fmt: skip
    r = verify(p, Chunk(text, 0, "profile"), DocContext("other", week, c.fiscal_year_end or "0331", text))
    if not isinstance(r, Candidate):
        return 0
    facts_repo.insert_facts(conn, c.id, doc_id, [(r, f"{provider}:{model}")])
    return 1


# ---------------------------------------------------------------- the brief


def brief(conn: psycopg.Connection[Any], week: date) -> str:
    until = cutoff_for(week)  # the week's window: [cutoff - 7 days, cutoff), so an item is in one brief (R2-F6)
    since = until - timedelta(days=7)
    now = {r["category"]: r for r in facts_repo.capex_index(conn, week)}
    prev = {r["category"]: r for r in facts_repo.capex_index(conn, week - timedelta(days=7))
            if r["week_end"] < week}  # fmt: skip
    moves = [IndexMove(k, r["value"], r["direction"], prev[k]["value"] if k in prev else None,
                       prev[k]["direction"] if k in prev else None) for k, r in now.items()]  # fmt: skip
    new = [NewFact(r["company"], r["fact_type"], r["subject_key"], r["computed_note"], r["change_kind"], r["quote"],
                   r["url"], abs(r["delta_pct"]) if r["delta_pct"] is not None else
                   (Decimal(100) if r["change_kind"] == "new" and r["value_num"] is not None else Decimal(0)))
           for r in facts_repo.new_diffs(conn, since, until)]  # fmt: skip
    links = [(r["company"], r["entity"], r["relation"]) for r in facts_repo.new_links(conn, since, until)]
    members = [
        (r["company"], r["category"], r["quote"] or "") for r in facts_repo.new_memberships(conn, since, until, "p06")
    ]
    s11 = [(r["company"], r["inputs"]) for r in facts_repo.fired_signal(conn, week, "S11")]
    return render(week, moves, new, links, members, s11)


# ---------------------------------------------------------------- the run


def last_friday(d: date) -> date:
    return d - timedelta(days=(d.weekday() - 4) % 7)


def run_index(conn: psycopg.Connection[Any], week: date, http: HttpClient, nse: NseClient | None, router: Router,
              settings: Settings) -> CapexStats:  # fmt: skip
    from pipeline.facts.run import scope as text_scope

    stats = CapexStats(week.isoformat())
    cfg = config()
    companies = [c for c in repo.companies(conn) if c.id is not None]
    with conn.transaction():
        ingest_eia(conn, http, settings.eia_api_key, week, stats)
    with conn.transaction():
        build_index(conn, week, companies, cfg, stats)
    with conn.transaction():
        propose_us(conn, companies, cfg, facts_repo.ledger_companies(conn), stats)
    with conn.transaction():
        cross_border(conn, router, nse, companies, set(text_scope(conn, companies)), week, cfg,
                     settings.cache_dir / "raw", stats)  # fmt: skip
    stats.errors = stats.errors[:50]
    return stats


def main(argv: list[str] | None = None) -> int:
    from pipeline.llm.clients import providers
    from pipeline.llm.quotas import Quotas
    from pipeline.llm.router import CallRecord

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=("index", "brief"), required=True)
    ap.add_argument("--week", type=date.fromisoformat, default=last_friday(datetime.now(UTC).date()))
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    with psycopg.connect(settings.database_url) as conn, repo.tracked_run(conn, f"capex_{a.stage}") as tracked:
        if a.stage == "brief":
            body = brief(conn, a.week)
            with conn.transaction():
                facts_repo.upsert_capex_brief(conn, a.week, body)
            tracked.update({"chars": len(body)})
            print(body)
            return 0
        quotas = Quotas.load()
        http = HttpClient(settings)

        def log(r: CallRecord) -> None:
            from pipeline.db.models import LlmCall

            facts_repo.record_llm_calls(conn, [LlmCall(**asdict(r))])

        router = Router(providers(http, settings, quotas), quotas, log=log,
                        used_today=facts_repo.llm_usage(conn, datetime.now(UTC).date()))  # fmt: skip
        stats = run_index(conn, a.week, http, NseClient(http), router, settings)
        tracked.update(asdict(stats))
    print(f"capex {a.week}: rising {', '.join(stats.rising) or 'none'}; proposals US {stats.proposed_us}, "
          f"India {stats.proposed_in}; export facts {stats.export_facts}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())

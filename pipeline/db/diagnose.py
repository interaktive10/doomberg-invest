"""Why a scored week's companies landed in their buckets (BRIEF §4.8), read-only. For the candidate stage (Evidence
>= 40) per market: how many were priced, which signal families contributed, how many had two families (Evidence
above the single-family cap of 55 needs them), each of C1-C3, a Gap, a market cap above the §1.3 floor; why the
priced ones that aren't candidates aren't; the top of the stage with its numbers; the last scoring run's errors by
source (a source that failed, such as the price source or a benchmark, shows here); the last text run's line: its
scope, what it queued and read, and why it stopped (docs/SPEC_ISSUES.md 50); and S9's fires with the quote behind
each, to audit by eye before a Candidate it made is trusted (docs/SPEC_ISSUES.md 58).

`python -m pipeline.db.diagnose [--week YYYY-MM-DD]` (default: the latest scored week); the manual workflow
diagnose.yml runs it against the live database. Market data only: no journal, positions or post-mortems, and no
name with a thesis or research entry in the S9 lines (the repository's logs are public)."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg

from pipeline.settings import Settings
from pipeline.signals.buckets import market_cap_ok

CONTEXT = ("C1", "C2", "C3")  # C4 went with GDELT (docs/SPEC_ISSUES.md 48)
STAGE_SQL = """
select c.market, coalesce(c.ticker, c.nse_symbol, c.name) as symbol, s.evidence, s.gap, s.bucket, s.families,
       m.metrics ->> 'market_cap' as market_cap,
       (select jsonb_object_agg(v.metric_id, v.inputs -> 'score') from context_values v
         where v.company_id = s.company_id and v.week_end = s.week_end) as context
from scores s
join companies c on c.id = s.company_id
left join company_metrics m on m.company_id = s.company_id and m.week_end = s.week_end
where s.week_end = %s and s.evidence >= %s
order by s.evidence desc, symbol
"""


LAST_RUN_SQL = """
select started_at, status, stats -> 'errors' from runs
where kind = 'scores_weekly' and finished_at is not null order by started_at desc limit 1
"""
TEXT_RUN_SQL = """
select started_at, status, stats, error from runs
where kind = 'text' and finished_at is not null order by started_at desc limit 1
"""
# S9's fires of the week, each with its newest qualifying-type verified fact the week could read (point in time); a
# name with any theses row (a thesis, research entry or position, live or closed) is only counted
S9_SQL = """
select c.market, coalesce(c.ticker, c.nse_symbol, c.name) as symbol, s.bucket, s.evidence,
       (v.inputs ->> 'count')::int as facts, x.fact_type, x.kind, x.published_at, x.quote,
       exists (select 1 from theses t where t.company_id = v.company_id) as private
from signal_values v
join companies c on c.id = v.company_id
join scores s on s.company_id = v.company_id and s.week_end = v.week_end
left join lateral (
  select f.fact_type, d.kind, d.published_at, f.quote from facts f join documents d on d.id = f.document_id
   where f.company_id = v.company_id and f.verification_status = 'verified' and d.published_at < %(cutoff)s
     and f.fact_type = any(%(types)s) and f.as_of between %(since)s and %(week)s
   order by f.as_of desc, d.published_at desc, f.id limit 1) x on true
where v.week_end = %(week)s and v.signal_id = 'S9' and v.fired
order by c.market desc, s.evidence desc, symbol
"""


def _num(x: Any) -> Decimal | None:
    return None if x is None else Decimal(str(x))


@dataclass(frozen=True)
class Row:
    market: str
    symbol: str
    evidence: Decimal
    gap: Decimal | None
    bucket: str
    families: tuple[str, ...]
    market_cap: Decimal | None
    context: Mapping[str, Decimal | None] = field(default_factory=dict)  # empty: not priced this week

    @classmethod
    def of(cls, r: Sequence[Any]) -> Row:
        ctx = {k: _num(v) for k, v in (r[7] or {}).items()}
        return cls(r[0], r[1], Decimal(str(r[2])), _num(r[3]), r[4], tuple(r[5] or ()), _num(r[6]), ctx)


def stage_rows(conn: psycopg.Connection[Any], week: date, stage_min: Decimal) -> list[Row]:
    return [Row.of(r) for r in conn.execute(STAGE_SQL, (week, stage_min)).fetchall()]


def why_not(r: Row, universe: Mapping[str, Mapping[str, Any]], buckets: Mapping[str, Any]) -> str:
    """The first rule of buckets.bucket() a priced company in 'none' fails."""
    early = buckets["early"]
    if r.gap is None:
        return "no Gap (fewer than 2 of C1-C3 known)"
    if r.market_cap is None:
        return "market cap unknown (no share count)"
    if not market_cap_ok(r.market, r.market_cap, universe):
        return "market cap below the floor"
    if len(r.families) < int(early["min_families"]):
        return "one signal family (Evidence capped at 55; early needs 2; not on Watch)"
    if r.gap < Decimal(str(early["min_gap"])):
        return "Gap below 50 with Evidence under 60"
    return "other"


def report(rows: Sequence[Row], universe: Mapping[str, Mapping[str, Any]], buckets: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for market in ("us", "in"):
        stage = [r for r in rows if r.market == market]
        if not stage:
            continue
        priced = [r for r in stage if r.context]
        fams = Counter(f for r in stage for f in r.families)
        n_fam = Counter(min(len(r.families), 3) for r in stage)
        out.append(
            f"{market}: stage {len(stage)}, priced {len(priced)}, buckets {dict(Counter(r.bucket for r in stage))}"
        )
        out.append(f"  families contributing: {dict(fams.most_common())}")
        out.append(f"  companies by number of families (3 = 3+): {dict(sorted(n_fam.items()))}")
        known = {m: sum(1 for r in priced if r.context.get(m) is not None) for m in CONTEXT}
        mcap = sum(1 for r in priced if r.market_cap is not None)
        floor = sum(1 for r in priced if market_cap_ok(market, r.market_cap, universe))
        gap = sum(1 for r in priced if r.gap is not None)
        out.append(f"  priced: context known {known}, Gap {gap}, market cap {mcap}, above the floor {floor}")
        none = Counter(why_not(r, universe, buckets) for r in priced if r.bucket == "none")
        out.append(f"  priced but 'none': {dict(none.most_common())}")
        out.append("  top of the stage (Evidence, families, Gap, C1-C3 scores, market cap in millions, bucket):")
        for r in stage[:15]:
            ctx = " ".join(f"{m}={'-' if r.context.get(m) is None else f'{r.context[m]:.0f}'}" for m in CONTEXT)
            cap = "-" if r.market_cap is None else f"{r.market_cap / 1_000_000:,.0f}"
            gap_s = "-" if r.gap is None else f"{r.gap:.1f}"
            out.append(
                f"    {r.symbol:<12} E={r.evidence:.1f} fam={'+'.join(r.families) or '-'} Gap={gap_s} {ctx} "
                f"mcap={cap} {r.bucket}"
            )
    return out


def run_errors(errors: Sequence[str], examples: int = 3) -> list[str]:
    """A scoring run's errors ("twelvedata PWR: TwelveDataUnavailable: ...") grouped by their source, with the first
    examples."""
    by: dict[str, list[str]] = {}
    for e in errors:
        by.setdefault(e.split(" ", 1)[0], []).append(e)
    out = []
    for source, items in sorted(by.items(), key=lambda kv: -len(kv[1])):
        out.append(f"  {source}: {len(items)}")
        out += [f"    {e[:200]}" for e in items[:examples]]
    return out


def last_run(conn: psycopg.Connection[Any]) -> list[str]:
    row = conn.execute(LAST_RUN_SQL).fetchone()
    if row is None:
        return ["last scoring run: none"]
    errors = [str(e) for e in (row[2] or [])]
    return [f"last scoring run {row[0]:%Y-%m-%d %H:%M}Z: {row[1]}, {len(errors)} errors", *run_errors(errors)]


def text_run(started: datetime, status: str, stats: Mapping[str, Any], error: str | None = None) -> str:
    """The daily text run's line (pipeline.facts.run.TextStats): its scope, what it queued and read, and why it
    stopped ("queue empty" when nothing stopped it)."""
    head = f"last text run {started:%Y-%m-%d %H:%M}Z: {status}"
    if status == "failed":
        return f"{head} ({(error or 'no error recorded')[:200]})"
    if "skipped" in stats:
        return f"{head}, skipped ({stats['skipped']})"

    def n(key: str) -> int:
        return int(stats.get(key) or 0)

    places = ""
    if stats.get("scope_by_order") or stats.get("read_by_order"):  # the reading order (docs/SPEC_ISSUES.md 58)
        places = f"; in scope by place {stats.get('scope_by_order') or {}}, read {stats.get('read_by_order') or {}}"
    return (f"{head}, scope {n('scope')} (theses {n('theses')}, stage names {n('stage')}), submissions read for "
            f"{n('submissions')} ({n('indexed')} in the EDGAR index), {n('queued_filings')} filings queued, "
            f"{n('skipped_filings')} skipped, {n('extracted')} documents extracted, {n('deferred')} deferred, "
            f"{n('failed')} failed, {n('facts_verified')} verified facts{places}; stopped: "
            f"{stats.get('stopped') or 'queue empty'}")  # fmt: skip


def last_text_run(conn: psycopg.Connection[Any]) -> list[str]:
    row = conn.execute(TEXT_RUN_SQL).fetchone()
    if row is None:
        return ["last text run: none"]
    return [text_run(row[0], row[1], row[2] or {}, row[3])]


QUOTE_CHARS = 160


def s9_audit(conn: psycopg.Connection[Any], week: date, s9: Mapping[str, Any], limit: int = 30) -> list[str]:
    """S9's fires this week by market and bucket, then up to `limit` of them with the newest verified fact behind each
    (its quote cut at QUOTE_CHARS): one fact is 20 Evidence points, so new Candidates are audited by eye before they
    are trusted (docs/SPEC_ISSUES.md 58). A name with a thesis or research entry is counted, never named."""
    from pipeline.db.pit import cutoff_for
    from pipeline.signals.base import months_before

    params = {"week": week, "cutoff": cutoff_for(week), "types": list(s9["fact_types"]),
              "since": months_before(week, 3 * int(s9["lookback_quarters"]))}  # fmt: skip
    rows = conn.execute(S9_SQL, params).fetchall()
    shown = [r for r in rows if not r[9]]

    def fired(market: str) -> str:
        by = Counter(r[2] for r in rows if r[0] == market)
        buckets = ", ".join(f"{b} {n}" for b, n in by.most_common())
        return f"{market} {sum(by.values())}" + (f" ({buckets})" if by else "")

    out = [f"S9 (verified text facts) fired: {fired('us')}, {fired('in')}; {len(rows) - len(shown)} of them a thesis "
           "or research entry's, not named here"]  # fmt: skip
    for market, symbol, bucket, evidence, facts, fact_type, kind, published, quote in (r[:9] for r in shown[:limit]):
        if quote is None:
            behind = "no fact found"
        else:
            cut = quote if len(quote) <= QUOTE_CHARS else quote[: QUOTE_CHARS - 1] + "…"
            behind = f"{fact_type} · {kind} {published:%Y-%m-%d} · “{cut}”"
        out.append(f"  {market} {symbol:<12} {bucket:<9} E={Decimal(str(evidence)):.1f} facts={facts}: {behind}")
    if len(shown) > limit:
        out.append(f"  ... and {len(shown) - limit} more")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--week", type=date.fromisoformat, default=None, help="Friday to inspect (default: the latest)")
    a = ap.parse_args(argv)
    from pipeline.signals.weekly import Configs

    cfgs = Configs.load()
    stage_min = Decimal(str(cfgs.signals["scores"]["us_price_candidate_min_evidence"]))
    with psycopg.connect(Settings.from_env().database_url) as conn:
        week = a.week or conn.execute("select max(week_end) from scores").fetchone()[0]  # type: ignore[index]
        text = last_text_run(conn)
        if week is None:
            print("diagnose: no scored week yet", *text, sep="\n")
            return 0
        rows = stage_rows(conn, week, stage_min)
        runs = last_run(conn)
        audit = s9_audit(conn, week, cfgs.signals["s9_text"])
    print(f"diagnose {week}:")
    for line in [*report(rows, cfgs.universe, cfgs.signals["scores"]["buckets"]), *runs, *text, *audit]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

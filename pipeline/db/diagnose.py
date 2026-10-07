"""Why a scored week's companies landed in their buckets (BRIEF §4.8), read-only. For the candidate stage (Evidence
>= 40) per market: how many were priced, which signal families contributed, how many had two families (Evidence
above the single-family cap of 55 needs them), each of C1-C4, a Gap, a market cap above the §1.3 floor; why the
priced ones that aren't candidates aren't; and the top of the stage with its numbers.

`python -m pipeline.db.diagnose [--week YYYY-MM-DD]` (default: the latest scored week); the manual workflow
diagnose.yml runs it against the live database. Market data only: no journal, positions or post-mortems."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from pipeline.settings import Settings
from pipeline.signals.buckets import market_cap_ok

CONTEXT = ("C1", "C2", "C3", "C4")
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
        return "no Gap (fewer than 2 of C1-C4 known)"
    if r.market_cap is None:
        return "market cap unknown (no share count)"
    if not market_cap_ok(r.market, r.market_cap, universe):
        return "market cap below the floor"
    if len(r.families) < int(early["min_families"]):
        return "one signal family (Evidence capped at 55; early needs 2)"
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
        out.append("  top of the stage (Evidence, families, Gap, C1-C4 scores, market cap in millions, bucket):")
        for r in stage[:15]:
            ctx = " ".join(f"{m}={'-' if r.context.get(m) is None else f'{r.context[m]:.0f}'}" for m in CONTEXT)
            cap = "-" if r.market_cap is None else f"{r.market_cap / 1_000_000:,.0f}"
            gap_s = "-" if r.gap is None else f"{r.gap:.1f}"
            out.append(
                f"    {r.symbol:<12} E={r.evidence:.1f} fam={'+'.join(r.families) or '-'} Gap={gap_s} {ctx} "
                f"mcap={cap} {r.bucket}"
            )
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
        if week is None:
            print("diagnose: no scored week yet")
            return 0
        rows = stage_rows(conn, week, stage_min)
    print(f"diagnose {week}:")
    for line in report(rows, cfgs.universe, cfgs.signals["scores"]["buckets"]):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

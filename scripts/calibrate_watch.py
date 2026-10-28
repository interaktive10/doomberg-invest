"""Read-only calibration report for the Watch list and the India restart (scratch branch, never merged).
Market data only: no journal, positions or post-mortems."""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

import psycopg

Q: dict[str, str] = {}


def rows(cur: Any, sql: str, *args: Any) -> list[tuple[Any, ...]]:
    cur.execute(sql, args)
    return list(cur.fetchall())


def main() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        for market in ("us", "in"):
            wk = rows(cur, """select max(s.week_end) from scores s join companies c on c.id = s.company_id
                              where c.market = %s""", market)[0][0]
            print(f"\n================ {market}: latest scored week {wk}")
            if wk is None:
                continue
            print("universe:", rows(cur, "select count(*) filter (where in_universe), count(*) from companies where market = %s", market))
            print("buckets:", rows(cur, """select s.bucket, count(*) from scores s join companies c on c.id = s.company_id
                                            where c.market = %s and s.week_end = %s group by 1 order by 2 desc""", market, wk))
            print("scored weeks (last 8):", rows(cur, """select s.week_end, count(*), count(*) filter (where s.bucket='candidate')
                    from scores s join companies c on c.id = s.company_id where c.market = %s
                    group by 1 order by 1 desc limit 8""", market))
            # signal firing, all scored and stage
            fired = rows(cur, """select v.signal_id, count(*), count(*) filter (where s.evidence >= 40),
                       round(avg(v.strength), 3), min(v.strength), max(v.strength)
                       from signal_values v join companies c on c.id = v.company_id
                       join scores s on s.company_id = v.company_id and s.week_end = v.week_end
                       where c.market = %s and v.week_end = %s and v.fired group by 1 order by 1""", market, wk)
            print("signals fired (id, all, in stage, avg/min/max strength):")
            for r in fired:
                print("   ", r)
            print("red flags fired (id, hard, n):", rows(cur, """select f.flag_id, f.hard, count(*) from redflag_values f
                    join companies c on c.id = f.company_id where c.market = %s and f.week_end = %s
                    and f.inputs->>'status' = 'fired' group by 1, 2 order by 1""", market, wk))
            # evidence histogram by family count
            hist = rows(cur, """select cardinality(s.families) as nf,
                       case when s.evidence < 40 then '<40' when s.evidence < 45 then '40-45' when s.evidence < 50 then '45-50'
                            when s.evidence = 50 then '=50' when s.evidence <= 55 then '50-55' when s.evidence < 60 then '55-60'
                            else '60+' end as band, count(*)
                       from scores s join companies c on c.id = s.company_id
                       where c.market = %s and s.week_end = %s and cardinality(s.families) > 0 group by 1, 2 order by 1, 2""", market, wk)
            print("evidence bands by families:", hist)
            # signal combos among single-family names in stage
            combos = rows(cur, """select string_agg(v.signal_id, '+' order by v.signal_id) as combo, s.evidence
                       from scores s join companies c on c.id = s.company_id
                       join signal_values v on v.company_id = s.company_id and v.week_end = s.week_end and v.fired
                       where c.market = %s and s.week_end = %s and s.evidence >= 40 and cardinality(s.families) = 1
                       group by s.company_id, s.evidence""", market, wk)
            cc = Counter((c, str(e)) for c, e in combos)
            print("single-family stage: signal combo x evidence (top 20):")
            for (c, e), n in cc.most_common(20):
                print(f"    {c:20s} E={e:6s} n={n}")
            # watch calibration: single family, priced, mcap known
            floor = "300000000" if market == "us" else "5000000000"
            cal = rows(cur, f"""select count(*) filter (where s.evidence >= 50),
                       count(*) filter (where s.evidence >= 50 and s.gap is not null),
                       count(*) filter (where s.evidence >= 50 and s.gap >= 50),
                       count(*) filter (where s.evidence >= 50 and s.gap >= 60),
                       count(*) filter (where s.evidence >= 50 and s.gap >= 70),
                       count(*) filter (where s.evidence >= 50 and s.gap >= 60 and (m.metrics->>'market_cap')::numeric >= {floor}),
                       count(*) filter (where s.evidence >= 45 and s.gap >= 60 and (m.metrics->>'market_cap')::numeric >= {floor}),
                       count(*) filter (where s.evidence > 50 and s.gap >= 50 and (m.metrics->>'market_cap')::numeric >= {floor})
                       from scores s join companies c on c.id = s.company_id
                       left join company_metrics m on m.company_id = s.company_id and m.week_end = s.week_end
                       where c.market = %s and s.week_end = %s and cardinality(s.families) = 1 and s.bucket <> 'excluded'""", market, wk)
            print("single-family, not excluded: E>=50 | +gap known | gap>=50 | >=60 | >=70 | gap>=60&mcap ok | E>=45&gap>=60&mcap | E>50&gap>=50&mcap:", cal)
            top = rows(cur, f"""select coalesce(c.ticker, c.nse_symbol, c.name), s.evidence, s.gap, s.families,
                       (select string_agg(v.signal_id || ':' || round(v.strength, 2)::text, ' ' order by v.signal_id) from signal_values v
                         where v.company_id = s.company_id and v.week_end = s.week_end and v.fired),
                       round(((m.metrics->>'market_cap')::numeric / 1e6)::numeric, 0),
                       (select jsonb_object_agg(x.metric_id, round(coalesce(x.pct, 0)::numeric, 0)) from context_values x
                         where x.company_id = s.company_id and x.week_end = s.week_end),
                       c.sector
                       from scores s join companies c on c.id = s.company_id
                       left join company_metrics m on m.company_id = s.company_id and m.week_end = s.week_end
                       where c.market = %s and s.week_end = %s and cardinality(s.families) = 1 and s.bucket <> 'excluded'
                         and s.evidence >= 50 and s.gap >= 50 and (m.metrics->>'market_cap')::numeric >= {floor}
                       order by s.gap desc limit 40""", market, wk)
            print("top 40 single-family by Gap (E>=50, Gap>=50, mcap ok):")
            for r in top:
                print("   ", r)
            two = rows(cur, """select coalesce(c.ticker, c.nse_symbol, c.name), s.evidence, s.gap, s.families, s.bucket
                       from scores s join companies c on c.id = s.company_id
                       where c.market = %s and s.week_end = %s and cardinality(s.families) >= 2 order by s.evidence desc""", market, wk)
            print("two+ family names:", two)
            # novelty: names whose evidence crossed 40 this week
            prev = rows(cur, """select count(*) from scores s join companies c on c.id = s.company_id
                       where c.market = %s and s.week_end = %s and s.evidence >= 40
                       and not exists (select 1 from scores p where p.company_id = s.company_id and p.week_end = %s::date - 7 and p.evidence >= 40)""",
                        market, wk, wk)
            print("stage names new this week:", prev)
            # data coverage
            print("prices_w: latest week, companies at latest:", rows(cur, """select max(p.week_end), count(*) filter (where p.week_end = (select max(week_end) from prices_w p2 join companies c2 on c2.id = p2.company_id where c2.market = %s))
                    from prices_w p join companies c on c.id = p.company_id where c.market = %s""", market, market))
            print("fundamentals_q: latest period, companies with a row in last 200 days of filings:", rows(cur, """select max(f.period_end),
                    count(distinct f.company_id) filter (where f.period_end >= current_date - 200)
                    from fundamentals_q f join companies c on c.id = f.company_id where c.market = %s""", market))
            print("ownership_q latest quarter, companies:", rows(cur, """select o.quarter_end, count(*) from ownership_q o join companies c on c.id = o.company_id
                    where c.market = %s group by 1 order by 1 desc limit 3""", market))
            print("insider_events last 120 days by kind:", rows(cur, """select i.kind, count(*) from insider_events i join companies c on c.id = i.company_id
                    where c.market = %s and i.txn_date >= current_date - 120 group by 1 order by 2 desc limit 8""", market) if False else "skipped")
            print("facts by status (last 180 days of as_of):", rows(cur, """select f.verification_status, count(*), count(distinct f.company_id)
                    from facts f join companies c on c.id = f.company_id where c.market = %s and f.as_of >= current_date - 180
                    and f.superseded_by is null group by 1""", market))
            print("verified facts by type (last 180 days):", rows(cur, """select f.fact_type, count(*), count(distinct f.company_id)
                    from facts f join companies c on c.id = f.company_id where c.market = %s and f.as_of >= current_date - 180
                    and f.superseded_by is null and f.verification_status = 'verified' group by 1 order by 2 desc""", market))
            print("stage names with >=1 verified fact in 180 days:", rows(cur, """select count(distinct s.company_id) from scores s
                    join companies c on c.id = s.company_id join facts f on f.company_id = s.company_id
                    where c.market = %s and s.week_end = %s and s.evidence >= 40 and f.verification_status = 'verified'
                    and f.superseded_by is null and f.as_of >= current_date - 180""", market, wk))
            print("S9 inputs sample (not fired, count>0 or facts present):", rows(cur, """select coalesce(c.ticker, c.nse_symbol), v.inputs
                    from signal_values v join companies c on c.id = v.company_id where c.market = %s and v.week_end = %s
                    and v.signal_id = 'S9' and exists (select 1 from facts f where f.company_id = v.company_id and f.verification_status='verified')
                    limit 8""", market, wk))
            print("S12 inputs sample:", rows(cur, """select coalesce(c.ticker, c.nse_symbol), v.fired, v.inputs from signal_values v
                    join companies c on c.id = v.company_id where c.market = %s and v.week_end = %s and v.signal_id = 'S12'
                    and v.inputs::text <> '{}' limit 5""", market, wk))
        print("\nsource_health:", rows(cur, "select source, last_success, stale, left(coalesce(last_error, ''), 120) from source_health order by source"))
        print("runs (last 12):", rows(cur, "select kind, started_at, status from runs order by started_at desc limit 12"))


if __name__ == "__main__":
    main()

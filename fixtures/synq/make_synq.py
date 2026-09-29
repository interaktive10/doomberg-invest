#!/usr/bin/env python3
"""F-SYNQ (BRIEF §9): synthetic quarterly series with a true, a false and a just-below-threshold case for every
signal S1-S12 and red flag R1-R6 (M4-01). Deterministic; writes fixtures/synq/cases.json.

`python fixtures/synq/make_synq.py` rewrites the file; `--check` exits 1 if it differs from the committed one.

Every case starts from one plain company (20 quarters to 2026-06-30, flat numbers) and overrides a few columns by
lag (lag 0 = the latest quarter). The as-of week is Friday 2026-09-18. Values are decimal strings so thresholds
compare exactly; the boundary cases sit just below a threshold (or just outside a window)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent / "cases.json"
WEEK = date(2026, 9, 18)
LATEST = date(2026, 6, 30)
N = 20
BASE = {
    "revenue": "1000", "op_income": "100", "net_income": "75", "pretax_income": "100", "tax_expense": "20",
    "cfo": "100", "capex": "40", "da": "30", "interest_expense": "5", "total_assets": "10000", "cash": "1000",
    "total_debt": "2000", "equity": "5000", "receivables": "500", "inventory": "300", "deferred_revenue": None,
    "rpo": None, "diluted_shares": "100", "shares_outstanding": "100",
}  # fmt: skip
Lags = dict[tuple[int, int], str | None]  # inclusive lag range -> value


def quarter_ends(n: int = N, latest: date = LATEST) -> list[date]:
    """Calendar quarter ends, oldest first."""
    out, y, m = [], latest.year, latest.month
    for _ in range(n):
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)) if m != 12 else date(y, 12, 31)
        out.append(last)
        m -= 3
        if m <= 0:
            m += 12
            y -= 1
    return out[::-1]


def quarters(**cols: Lags) -> list[dict[str, Any]]:
    ends = quarter_ends()
    rows = []
    for i, end in enumerate(ends):
        lag = len(ends) - 1 - i
        values = dict(BASE)
        for col, ranges in cols.items():
            for (lo, hi), v in ranges.items():
                if lo <= lag <= hi:
                    values[col] = v
        rows.append({"end": end.isoformat(), "values": values})
    return rows


def ago(days: int) -> str:
    return (WEEK - timedelta(days=days)).isoformat()


def months_ago(months: int, extra_days: int = 0) -> str:
    y, m = divmod(WEEK.year * 12 + WEEK.month - 1 - months, 12)
    return (date(y, m + 1, WEEK.day) - timedelta(days=extra_days)).isoformat()


def case(cid: str, target: str, kind: str, fired: bool, strength: str | None = None, *, market: str = "us",
         q: list[dict[str, Any]] | None = None, **ctx: Any) -> dict[str, Any]:  # fmt: skip
    return {"id": cid, "target": target, "kind": kind, "market": market, "week": WEEK.isoformat(),
            "expect": {"fired": fired, "strength": strength}, "quarters": q if q is not None else quarters(), **ctx}  # fmt: skip


ALL = (0, N - 1)


def s1() -> list[dict[str, Any]]:
    def book(lag0: str, lag1: str) -> list[dict[str, Any]]:
        return quarters(rpo={ALL: "1000", (0, 0): lag0, (1, 1): lag1})

    return [
        case("S1-true", "S1", "true", True, "1", q=book("1300", "1250")),  # gaps 0.30 / 0.25 vs flat revenue
        case("S1-false", "S1", "false", False, q=book("1050", "1050")),  # order book +5% only
        case("S1-boundary", "S1", "boundary", False, q=book("1300", "1099.9")),  # second quarter gap 0.0999
        case("S1-at-threshold", "S1", "true", True, "1", q=book("1300", "1100")),  # exactly 0.10 fires
    ]


def s2() -> list[dict[str, Any]]:
    def roic(op_recent: str) -> list[dict[str, Any]]:
        op = {ALL: "125", (0, 3): op_recent, (4, 7): "200", (8, 11): "100"}
        tax = {ALL: "25", (0, 3): str(round(float(op_recent) * 0.2, 6)), (4, 7): "40", (8, 11): "20"}
        eq = {ALL: "6000", (0, 3): "8000", (4, 7): "7500", (8, 11): "7000"}
        return quarters(op_income=op, pretax_income=op, tax_expense=tax, equity=eq, total_assets=eq,
                        total_debt={ALL: "0"}, cash={ALL: "0"}, revenue={ALL: "2500"})  # fmt: skip

    return [
        case("S2-true", "S2", "true", True, "0.6", q=roic("250")),  # IncROIC 0.20, ROIC 0.10 (0.0457 8q ago)
        case("S2-false", "S2", "false", False, q=roic("400")),  # ROIC 0.16: above the 0.03-0.12 band
        case("S2-boundary", "S2", "boundary", False, q=roic("218.6875")),  # IncROIC 0.1499
    ]


def s3() -> list[dict[str, Any]]:
    rev = {ALL: "1000", (0, 0): "1100", (1, 1): "1060", (2, 2): "1030"}  # quarterly YoY 0.10 > 0.06 > 0.03

    def lev(op0: str, revenue: Lags = rev) -> list[dict[str, Any]]:
        return quarters(revenue=revenue, op_income={ALL: "100", (0, 0): op0, (1, 1): "125", (2, 2): "110"})

    decelerating = {ALL: "1000", (0, 0): "1030", (1, 1): "1060", (2, 2): "1100"}
    return [
        case("S3-true", "S3", "true", True, "0.24343675", q=lev("135")),  # dOPM 0.0121718
        case("S3-false", "S3", "false", False, q=lev("135", decelerating)),  # growth slowing
        case("S3-boundary", "S3", "boundary", False, q=lev("125.481")),  # dOPM 0.0099
    ]


def s4() -> list[dict[str, Any]]:
    def cash(recent: str) -> list[dict[str, Any]]:
        return quarters(net_income={ALL: "100"}, cfo={ALL: "100", (0, 3): recent})

    return [
        case("S4-true", "S4", "true", True, "0.5", q=cash("125")),  # CCR 1.25 vs 1.00, Sloan -0.01 vs 0
        case("S4-false", "S4", "false", False, q=cash("90")),  # CCR 0.9
        case("S4-boundary", "S4", "boundary", False, q=cash("119.99")),  # CCR up 0.1999
    ]


def s5() -> list[dict[str, Any]]:
    def buyback(recent: str) -> list[dict[str, Any]]:
        return quarters(diluted_shares={ALL: "100", (0, 3): recent}, cfo={ALL: "150"}, capex={ALL: "50"})

    b = quarters(diluted_shares={ALL: "100", (0, 7): "121", (8, 11): "110"}, cfo={ALL: "150"}, capex={ALL: "50"})
    return [
        case("S5-true", "S5", "true", True, "0.5", q=buyback("97")),  # path A: -3% with FCF > 0
        case("S5-true-b", "S5", "true", True, "0.6", q=b),  # path B: +10%, +10%, then 0%
        case("S5-false", "S5", "false", False, q=buyback("99")),  # -1%
        case("S5-boundary", "S5", "boundary", False, q=buyback("98.01")),  # -1.99%
    ]


def s6() -> list[dict[str, Any]]:
    def derisk(past_debt: str, now_debt: str) -> list[dict[str, Any]]:
        debt = {ALL: "1000", (0, 0): now_debt, (4, 8): past_debt}
        return quarters(op_income={ALL: "100"}, da={ALL: "25"}, interest_expense={ALL: "20"}, cash={ALL: "0"},
                        total_debt=debt)  # fmt: skip

    return [
        case("S6-true", "S6", "true", True, "0.8", q=derisk("1600", "700")),  # 3.2x -> 1.4x, coverage 5.0
        case("S6-false", "S6", "false", False, q=derisk("1600", "1000")),  # still 2.0x
        case("S6-boundary", "S6", "boundary", False, q=derisk("1495", "700")),  # past max 2.99x
    ]


def s7() -> list[dict[str, Any]]:
    def buys(*lots: tuple[str, str, int, bool]) -> list[dict[str, Any]]:
        return [{"person": p, "value": v, "event_date": ago(d), "filed_at": ago(d - 2) + "T21:00:00+00:00",
                 "kind": "open_market_buy", "planned": planned, "source_url": f"https://www.sec.gov/f4/{p}/{d}"}
                for p, v, d, planned in lots]  # fmt: skip

    pledge = [{"quarter_end": "2026-03-31", "promoter_pledged_pct": "30"},
              {"quarter_end": "2026-06-30", "promoter_pledged_pct": "24"}]  # fmt: skip
    promoter = [{"person": "Promoter Holdings Pvt Ltd", "value": "30000000", "event_date": ago(20),
                 "filed_at": ago(18) + "T12:00:00+00:00", "kind": "promoter_buy", "planned": False,
                 "source_url": "https://nsearchives.nseindia.com/pit/1.xml"}]  # fmt: skip
    return [
        case("S7-true", "S7", "true", True, "0.51110313", insiders=buys(("A", "150000", 30, False), ("B", "120000", 10, False))),
        case("S7-false", "S7", "false", False, insiders=buys(("A", "300000", 30, False), ("B", "90000", 5, True))),
        case("S7-boundary", "S7", "boundary", False, insiders=buys(("A", "150000", 30, False), ("B", "99999", 10, False))),
        case("S7-in-pledge", "S7", "true", True, "0.6", market="in", ownership=pledge),
        case("S7-in-promoter", "S7", "true", True, "0.45849625", market="in", insiders=promoter),
    ]  # fmt: skip


def s8() -> list[dict[str, Any]]:
    def holders(*counts: int) -> list[dict[str, Any]]:
        ends = ["2025-12-31", "2026-03-31", "2026-06-30"]
        return [{"quarter_end": e, "inst_holders": c} for e, c in zip(ends, counts, strict=True)]

    fii = [{"quarter_end": e, "fii_pct": f, "dii_pct": "5"} for e, f in
           (("2025-12-31", "5"), ("2026-03-31", "6"), ("2026-06-30", "7.5"))]  # fmt: skip
    return [
        case("S8-true", "S8", "true", True, "0.30086957", ownership=holders(1000, 1150, 1323), holder_pct_in_size_decile="30"),
        case("S8-false", "S8", "false", False, ownership=holders(1000, 1150, 1323), holder_pct_in_size_decile="60"),
        case("S8-boundary", "S8", "boundary", False, ownership=holders(1000, 1150, 1322), holder_pct_in_size_decile="30"),
        case("S8-in-true", "S8", "true", True, "0.41666667", market="in", ownership=fii),
    ]  # fmt: skip


def s9() -> list[dict[str, Any]]:
    win = {"fact_type": "order_win", "subject_key": "order:grid", "as_of": ago(30), "counterparty": "Utility Co"}
    plain = {"fact_type": "capacity_addition", "subject_key": "capacity:mw:site_a", "as_of": ago(30)}
    old_win = {**win, "as_of": months_ago(6, extra_days=1)}
    return [
        case("S9-true", "S9", "true", True, "0.4", facts=[win, {**win, "as_of": ago(10)}]),  # restated: counts once
        case("S9-false", "S9", "false", False, facts=[plain]),  # no named counterparty or commitment
        case("S9-boundary", "S9", "boundary", False, facts=[old_win]),  # a day before the 2-quarter window
    ]


def s10() -> list[dict[str, Any]]:
    return [
        case("S10-true", "S10", "true", True, "0.6", events=[{"kind": "spinoff", "event_date": months_ago(12)}]),
        case("S10-false", "S10", "false", False, events=[{"kind": "spinoff", "event_date": months_ago(19)}]),
        case("S10-boundary", "S10", "boundary", False, events=[{"kind": "spinoff", "event_date": months_ago(18, 1)}]),
        case("S10-at-threshold", "S10", "true", True, "0.6", events=[{"kind": "spinoff", "event_date": months_ago(18)}]),
    ]  # fmt: skip


def s11() -> list[dict[str, Any]]:
    grow = quarters(revenue={ALL: "1000", (0, 3): "1050"})  # TTM revenue +5%

    def capex(direction: str, input_growth: str) -> dict[str, Any]:
        return {"categories": ["grid"], "direction": {"grid": direction}, "input_growth": {"grid": input_growth}}

    return [
        case("S11-true", "S11", "true", True, "0.75", q=grow, capex=capex("rising", "0.30"), prior={"S1": True}),
        case("S11-false", "S11", "false", False, q=grow, capex=capex("flat", "0.30"), prior={"S1": True}),
        case("S11-boundary", "S11", "boundary", False, q=grow, capex=capex("rising", "0.1499"), prior={"S1": True}),
    ]


def s12() -> list[dict[str, Any]]:
    def sector(capex: list[str], tight: int) -> dict[str, Any]:
        return {"sector": "industrials", "capex_da_medians": capex, "revenue_yoy_medians": ["0.02", "0.01", "-0.01"],
                "tightness_facts": tight}  # fmt: skip

    return [
        case("S12-true", "S12", "true", True, "0.6", sector=sector(["0.9", "0.8", "0.95"], 2), prior={"S2": True}),
        case("S12-false", "S12", "false", False, sector=sector(["1.1", "0.8", "0.95"], 2), prior={"S2": True}),
        case("S12-boundary", "S12", "boundary", False, sector=sector(["0.9", "0.8", "0.95"], 1), prior={"S2": True}),
    ]


def flags() -> list[dict[str, Any]]:
    def cfo(v: str) -> list[dict[str, Any]]:
        return quarters(net_income={ALL: "100"}, cfo={ALL: v})

    def receivables(now: str) -> list[dict[str, Any]]:
        return quarters(receivables={ALL: "1000", (0, 0): now})

    def shares(now: str) -> list[dict[str, Any]]:
        return quarters(diluted_shares={ALL: "100", (0, 3): now})

    def burn(nd4: str) -> list[dict[str, Any]]:
        debt = {ALL: "500", (0, 0): "900", (1, 1): "800", (2, 2): "700", (3, 3): "600", (4, 4): nd4}
        return quarters(cash={ALL: "0"}, total_debt=debt, cfo={ALL: "-50"}, capex={ALL: "50"})

    auditor = [{"kind": "auditor_change", "event_date": months_ago(3)}]
    deal = [{"kind": "acquisition", "event_date": months_ago(3)}]
    pledged = [{"quarter_end": "2026-06-30", "promoter_pledged_pct": p} for p in ("25", "5", "19.99")]
    return [
        case("R1-true", "R1", "true", True, q=cfo("37.5")),  # CFO/NI 0.375
        case("R1-false", "R1", "false", False, q=cfo("100")),
        case("R1-boundary", "R1", "boundary", False, q=cfo("50")),  # CFO/NI exactly 0.5 (the rule is < 0.5)
        case("R2-true", "R2", "true", True, q=receivables("1333")),  # +33.3 pp vs flat revenue
        case("R2-false", "R2", "false", False, q=receivables("1050")),
        case("R2-boundary", "R2", "boundary", False, q=receivables("1199.9")),  # +19.99 pp
        case("R3-true", "R3", "true", True, events=auditor),
        case("R3-false", "R3", "false", False),
        case("R3-boundary", "R3", "boundary", False, events=[{"kind": "auditor_change", "event_date": months_ago(12, 1)}]),
        case("R4-true", "R4", "true", True, q=shares("112")),
        case("R4-false", "R4", "false", False, q=shares("112"), events=deal),  # dilution from an acquisition
        case("R4-boundary", "R4", "boundary", False, q=shares("109.99")),
        case("R5-true", "R5", "true", True, market="in", ownership=[pledged[0]]),
        case("R5-false", "R5", "false", False, market="in", ownership=[pledged[1]]),
        case("R5-boundary", "R5", "boundary", False, market="in", ownership=[pledged[2]]),
        case("R6-true", "R6", "true", True, q=burn("500")),  # ND up 4 straight quarters, FCF < 0
        case("R6-false", "R6", "false", False, q=burn("500"), prior={"S1": True}),  # unless S1 fires
        case("R6-boundary", "R6", "boundary", False, q=burn("600")),  # only 3 straight rises
    ]  # fmt: skip


def build() -> list[dict[str, Any]]:
    return [*s1(), *s2(), *s3(), *s4(), *s5(), *s6(), *s7(), *s8(), *s9(), *s10(), *s11(), *s12(), *flags()]


def render() -> str:
    """Quarters store only the columns that differ from BASE (the loader merges them back)."""
    cases = build()
    for c in cases:
        for q in c["quarters"]:
            q["values"] = {k: v for k, v in q["values"].items() if BASE.get(k) != v}
    return json.dumps({"base": BASE, "cases": cases}, indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 1 if cases.json is out of date")
    a = ap.parse_args(argv)
    text = render()
    if a.check:
        return 0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(build())} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

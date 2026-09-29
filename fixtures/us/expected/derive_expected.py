"""Independent derivation of the M2-01 expected quarterized values for 3 F-US companies (BRIEF §8 M2, §9).

It does NOT import pipeline code. Values come from SEC's own `frame` tags in companyfacts: SEC picks one fact per
calendar quarter (CY2024Q1 = a ~3-month duration, CY2024Q1I = an instant) and one per calendar year (CY2024). Q4 is
not reported as a quarter, so it is computed by hand as FY - Q1 - Q2 - Q3; cash from operations is only reported
year-to-date after Q1, so its quarters are YTD differences. Spot-checked against the companies' published quarters
(fixtures/us/expected/README.md). Run from the repo root: python fixtures/us/expected/derive_expected.py
"""

import csv
import json
from datetime import date

COMPANIES = {"AAPL": "0000320193", "MSFT": "0000789019", "CAT": "0000018230"}
FLOW_CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "op_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
}
INSTANT_CONCEPTS = {"total_assets": ["Assets"], "cash": ["CashAndCashEquivalentsAtCarryingValue"]}
QUARTERS = 8


def days(f):
    return (date.fromisoformat(f["end"]) - date.fromisoformat(f["start"])).days


def main():
    for ticker, cik in COMPANIES.items():
        g = json.load(open(f"fixtures/us/companyfacts/CIK{cik}.json"))["facts"]["us-gaap"]
        sub = json.load(open(f"fixtures/us/submissions/CIK{cik}.json"))["filings"]["recent"]
        # fiscal quarter ends = report dates of the company's latest 10-Q/10-K filings
        reports = sorted({(rd, f) for rd, f in zip(sub["reportDate"], sub["form"]) if f in ("10-Q", "10-K") and rd})
        ends = [date.fromisoformat(rd) for rd, _ in reports][-QUARTERS:]
        forms = {date.fromisoformat(rd): f for rd, f in reports}

        def facts(concepts):
            for c in concepts:
                if c in g:
                    yield from g[c]["units"]["USD"]

        def quarter_frame(concepts, end):
            for f in facts(concepts):
                if f["end"] == str(end) and f.get("frame", "").startswith("CY") and "start" in f and 80 <= days(f) <= 100:
                    return f["val"]
            return None

        def annual(concepts, end):
            vals = [f["val"] for f in facts(concepts) if f["end"] == str(end) and "start" in f and 350 <= days(f) <= 380]
            return vals[-1] if vals else None

        def ytd(concepts, start, end):
            vals = [f["val"] for f in facts(concepts) if f.get("start") == str(start) and f["end"] == str(end)]
            return vals[-1] if vals else None

        rows = []
        for e in ends:
            row = {"ticker": ticker, "period_end": str(e)}
            is_q4 = forms[e] == "10-K"
            fy_start = None
            if is_q4:
                fy = [f for f in facts(FLOW_CONCEPTS["revenue"]) if f["end"] == str(e) and "start" in f and 350 <= days(f) <= 380]
                fy_start = fy[-1]["start"]
            for col, concepts in FLOW_CONCEPTS.items():
                if not is_q4:
                    row[col] = quarter_frame(concepts, e)
                    continue
                # Q4 = FY - Q1 - Q2 - Q3; the three earlier quarter ends are the 3-month frames inside the year
                qs = sorted((f["end"], f["val"]) for f in facts(concepts)
                            if f.get("frame", "").startswith("CY") and "start" in f and 80 <= days(f) <= 100
                            and fy_start < f["end"] < str(e))
                q123 = dict(qs)
                row[col] = annual(concepts, e) - sum(q123.values()) if len(q123) == 3 else None
            # CFO: Q1 is 3 months; later quarters are YTD - previous YTD; Q4 = FY - 9M YTD
            cfo = ["NetCashProvidedByUsedInOperatingActivities"]
            starts = sorted({f["start"] for f in facts(cfo) if f["end"] == str(e) and "start" in f})
            start = starts[0] if starts else None  # the fiscal-year start (the longest period ending here)
            ends_in_year = sorted({f["end"] for f in facts(cfo) if f.get("start") == start and f["end"] < str(e)})
            this = ytd(cfo, start, e)
            prev = ytd(cfo, start, ends_in_year[-1]) if ends_in_year else 0
            row["cfo"] = this - prev if this is not None and prev is not None else None
            for col, concepts in INSTANT_CONCEPTS.items():
                vals = [f["val"] for f in facts(concepts) if f["end"] == str(e) and "start" not in f]
                row[col] = vals[-1] if vals else None
            rows.append(row)
        with open(f"fixtures/us/expected/{ticker}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["ticker", "period_end", *FLOW_CONCEPTS, "cfo", *INSTANT_CONCEPTS])
            w.writeheader()
            w.writerows(rows)
        print(ticker, len(rows), "quarters ->", f"fixtures/us/expected/{ticker}.csv")


if __name__ == "__main__":
    main()

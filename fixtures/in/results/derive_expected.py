"""Independent derivation of the expected KEI fundamentals rows (BRIEF §8 M3-02). Does NOT import pipeline code.
Run from the repo root: `python fixtures/in/results/derive_expected.py`.

Method (different from the pipeline's, which matches contexts by their dates): the integrated-filing generator names
its contexts OneD (the quarter), FourD (year to date) and OneI (the period-end instant); values are read by those
ids with a regex. Rows follow BRIEF §4.3: quarterly P&L; balance sheet only at Q2/Q4 (half-yearly); CFO/capex as
half-year flows (Q2 = H1, Q4 = FY − H1); op_income = PBT + finance costs − other income; shares = paid-up capital /
face value. filed_at = the listing's creation_Date (IST) in UTC. KEI's FY2026 results were checked by hand against
the company's published statements (revenue ₹2,726 / ₹2,955 / ₹3,476 crore for Q2 / Q3 / Q4).
"""

import csv
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

D = "fixtures/in/results/"
IST = timezone(timedelta(hours=5, minutes=30))
FILES = [("KEI_FY2026Q2_consolidated.xml", "FY2026Q2", "1549479"), ("KEI_FY2026Q3_consolidated.xml", "FY2026Q3", "1607504"),
         ("KEI_FY2026Q4_consolidated.xml", "FY2026Q4", "1663459")]  # fmt: skip
PL = {"revenue": "RevenueFromOperations", "pretax_income": "ProfitBeforeTax", "tax_expense": "TaxExpense",
      "net_income": "ProfitLossForPeriod", "interest_expense": "FinanceCosts",
      "da": "DepreciationDepletionAndAmortisationExpense"}  # fmt: skip
BS = {"total_assets": "Assets", "cash": "CashAndCashEquivalents", "equity": "EquityAttributableToOwnersOfParent",
      "receivables": "TradeReceivablesCurrent", "inventory": "Inventories"}  # fmt: skip
COLUMNS = ["period_end", "fiscal_label", "filed_at", "revenue", "op_income", "net_income", "pretax_income",
           "tax_expense", "cfo", "capex", "da", "interest_expense", "total_assets", "cash", "total_debt", "equity",
           "receivables", "inventory", "shares_outstanding"]  # fmt: skip


def value(xml, name, ctx):
    m = re.search(rf'<[\w-]+:{name}\b[^>]*contextRef="{ctx}"[^>]*>([^<]+)<', xml)
    return Decimal(m.group(1).strip()) if m else None


listing = json.load(open(D + "index_KEI.json"))["data"]
created = {r["xbrl"].rsplit("_", 3)[-3]: r["creation_Date"] for r in listing}
rows, h1 = [], {}
for name, label, seq in FILES:
    x = open(D + name, encoding="utf-8").read()
    end = re.search(r"<[\w-]+:DateOfEndOfReportingPeriod[^>]*>([^<]+)<", x).group(1)
    row = {"period_end": end, "fiscal_label": label}
    ist = datetime.strptime(created[seq], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
    row["filed_at"] = ist.astimezone(timezone.utc).isoformat()
    for col, el in PL.items():
        row[col] = value(x, el, "OneD")
    row["op_income"] = row["pretax_income"] + row["interest_expense"] - value(x, "OtherIncome", "OneD")
    q = int(label[-1])
    if q in (2, 4):
        for col, el in BS.items():
            row[col] = value(x, el, "OneI")
        row["total_debt"] = (value(x, "BorrowingsNoncurrent", "OneI") or 0) + (value(x, "BorrowingsCurrent", "OneI") or 0)
        cfo = value(x, "CashFlowsFromUsedInOperatingActivities", "FourD")
        capex = value(x, "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "FourD")
        if q == 2:
            h1 = {"cfo": cfo, "capex": capex}
            row["cfo"], row["capex"] = cfo, capex
        else:
            row["cfo"], row["capex"] = cfo - h1["cfo"], capex - h1["capex"]
    row["shares_outstanding"] = value(x, "PaidUpValueOfEquityShareCapital", "OneD") / value(x, "FaceValueOfEquityShareCapital", "OneD")
    rows.append(row)
with open(D + "expected_KEI.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=COLUMNS)
    w.writeheader()
    for r in rows:
        w.writerow({c: ("" if r.get(c) is None else str(r[c])) for c in COLUMNS})
print(open(D + "expected_KEI.csv").read())

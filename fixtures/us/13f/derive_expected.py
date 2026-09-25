"""Independent derivation of the F-13F expected values (BRIEF §8 M2-05). Does NOT import pipeline code.
Run from the repo root: `python fixtures/us/13f/derive_expected.py`.

- expected_counts.csv: distinct 13F-HR filers per CUSIP for period 2024-12-31. Per filer, the latest RESTATEMENT
  amendment replaces the original; NEW HOLDINGS amendments filed after the base add to it. Put/call rows and PRN
  (principal amount) rows are dropped; a CUSIP is dropped when most of its rows' title of class is not common stock
  (preferred, warrants, rights, debt, options, non-partnership units).
- expected_mapping.csv: CUSIP -> company, reviewed by hand (REVIEWED below: 13F issuer name -> ticker, checked against
  the names in data/universe/us_tickers_exchange.json); the CIK comes from that snapshot.
"""

import collections
import csv
import json
import re
from datetime import datetime

D = "fixtures/us/13f/"
PERIOD = "31-DEC-2024"
HOLDINGS = ("13F HOLDINGS REPORT", "13F COMBINATION REPORT")
NOT_COMMON = re.compile(r"PFD|PREF|WTS?\b|WARRANT|RIGHT|NOTE|DEBT|CONV|BOND|\bOPT|PUT|CALL|\*W", re.I)


def not_common(title):
    if NOT_COMMON.search(title):
        return True
    unit = re.search(r"\bUNITS?\b", title, re.I)
    partnership = re.search(r"\b(COM|COMMON|LP|PARTN|PTN)", title, re.I)
    return bool(unit) and not partnership


cover = {r["ACCESSION_NUMBER"]: r for r in csv.DictReader(open(D + "COVERPAGE.tsv"), delimiter="\t")}
subs = list(csv.DictReader(open(D + "SUBMISSION.tsv"), delimiter="\t"))

kept, votes = [], collections.defaultdict(lambda: [0, 0])
for r in csv.DictReader(open(D + "INFOTABLE.tsv"), delimiter="\t"):
    if r["PUTCALL"].strip() or r["SSHPRNAMTTYPE"] == "PRN":
        continue
    kept.append(r)
    v = votes[r["CUSIP"].upper()]
    v[0] += bool(not_common(r["TITLEOFCLASS"]))
    v[1] += 1
rows = collections.defaultdict(list)
for r in kept:
    n, total = votes[r["CUSIP"].upper()]
    if 2 * n <= total:
        rows[r["ACCESSION_NUMBER"]].append(r)

by_filer = collections.defaultdict(list)
for s in subs:
    c = cover.get(s["ACCESSION_NUMBER"], {})
    if s["PERIODOFREPORT"] == PERIOD and s["SUBMISSIONTYPE"] in ("13F-HR", "13F-HR/A") and c.get("REPORTTYPE") in HOLDINGS:
        filed = datetime.strptime(s["FILING_DATE"], "%d-%b-%Y")
        by_filer[s["CIK"].zfill(10)].append((filed, s["ACCESSION_NUMBER"], s["SUBMISSIONTYPE"], c.get("AMENDMENTTYPE", "")))
holders = collections.defaultdict(set)
for cik, fs in by_filer.items():
    fs.sort()
    restated = [f for f in fs if f[3] == "RESTATEMENT"]
    base = restated[-1] if restated else [f for f in fs if f[2] == "13F-HR"][-1]
    for f in [base] + [f for f in fs if f[3] == "NEW HOLDINGS" and f[0] >= base[0]]:
        for r in rows[f[1]]:
            holders[r["CUSIP"].upper()].add(cik)
with open(D + "expected_counts.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["cusip", "holders"])
    for c in sorted(holders):
        w.writerow([c, len(holders[c])])
print(len(holders), "cusips;", sum(len(v) for v in holders.values()), "filer-holdings;",
      "restatements used:", sum(1 for fs in by_filer.values() if any(f[3] == "RESTATEMENT" for f in fs)),
      "new-holdings filers:", sum(1 for fs in by_filer.values() if any(f[3] == "NEW HOLDINGS" for f in fs)))

names = collections.defaultdict(collections.Counter)
for rs in rows.values():
    for r in rs:
        names[r["CUSIP"].upper()][r["NAMEOFISSUER"]] += 1
REVIEWED = {
    "ADVANCED MICRO DEVICES INC": "AMD", "ALPHABET INC": "GOOGL", "AMAZON COM INC": "AMZN", "AMPHENOL CORP NEW": "APH",
    "APPLE INC": "AAPL", "APPLIED MATLS INC": "AMAT", "ARISTA NETWORKS INC": "ANET", "ARTIVION INC": "AORT",
    "ASML HOLDING N V": "ASML", "BLOOM ENERGY CORP": "BE", "BROADCOM INC": "AVGO", "CATERPILLAR INC": "CAT",
    "CIENA CORP": "CIEN", "COHERENT CORP": "COHR", "COMFORT SYS USA INC": "FIX", "CONSTELLATION ENERGY CORP": "CEG",
    "CORNING INC": "GLW", "CUMMINS INC": "CMI", "DELL TECHNOLOGIES INC": "DELL", "DIGITAL RLTY TR INC": "DLR",
    "DOMINION ENERGY INC": "D", "DUKE ENERGY CORP NEW": "DUK", "EATON CORP PLC": "ETN", "EMCOR GROUP INC": "EME",
    "EQUINIX INC": "EQIX", "FLEX LTD": "FLEX", "FLUENCE ENERGY INC": "FLNC", "GE VERNOVA INC": "GEV",
    "GERON CORP": "GERN", "HEWLETT PACKARD ENTERPRISE C": "HPE", "HUBBELL INC": "HUBB", "INTEL CORP": "INTC",
    "IRON MTN INC DEL": "IRM", "JABIL INC": "JBL", "JOHNSON CTLS INTL PLC": "JCI", "KLA CORP": "KLAC",
    "LAM RESEARCH CORP": "LRCX", "LUMENTUM HLDGS INC": "LITE", "MARRIOTT VACATIONS WORLDWIDE": "VAC",
    "MARVELL TECHNOLOGY INC": "MRVL", "MASTEC INC": "MTZ", "META PLATFORMS INC": "META", "MICRON TECHNOLOGY INC": "MU",
    "MICROSOFT CORP": "MSFT", "MODINE MFG CO": "MOD", "NEXTERA ENERGY INC": "NEE", "NRG ENERGY INC": "NRG",
    "NVENT ELECTRIC PLC": "NVT", "NVIDIA CORPORATION": "NVDA", "ORACLE CORP": "ORCL", "POWELL INDS INC": "POWL",
    "PRIMORIS SVCS CORP": "PRIM", "QUANTA SVCS INC": "PWR", "SOUTHERN CO": "SO", "STERLING INFRASTRUCTURE INC": "STRL",
    "SUPER MICRO COMPUTER INC": "SMCI", "TAIWAN SEMICONDUCTOR MFG LTD": "TSM", "TALEN ENERGY CORP": "TLN",
    "TRANE TECHNOLOGIES PLC": "TT", "VERTIV HOLDINGS CO": "VRT", "VISTRA CORP": "VST", "WESTERN DIGITAL CORP": "WDC",
    "SEAGATE TECHNOLOGY HLDNGS P": "STX",
}
snap = json.load(open("data/universe/us_tickers_exchange.json"))
fields = snap["fields"]
tick = {r[fields.index("ticker")]: str(r[fields.index("cik")]).zfill(10) for r in snap["data"]}
missing = set()
with open(D + "expected_mapping.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["cusip", "issuer", "ticker", "cik"])
    for c in sorted(names):
        issuer = names[c].most_common(1)[0][0]
        t = REVIEWED.get(issuer)
        if t is None:
            missing.add(issuer)
            continue
        w.writerow([c, issuer, t, tick[t]])
print("not reviewed (no company in the sample or a mislabelled CUSIP):", sorted(missing))

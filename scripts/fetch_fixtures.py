#!/usr/bin/env python3
"""The only script allowed to use the network in tests/builds (BRIEF §9). Run once; results are committed.

  fetch_fixtures.py universe                # M0: SEC company_tickers_exchange.json + NSE EQUITY_L.csv -> data/universe/
  fetch_fixtures.py universe --source sec   # one source only (NSE often blocks cloud runners; SEC throttles shared IPs)
  fetch_fixtures.py f-us                    # M2: companyfacts + submissions for the 8 F-US companies -> fixtures/us/
  fetch_fixtures.py f-f4                    # M2: 10 real Form 4 submissions (.txt) -> fixtures/us/form4/
  fetch_fixtures.py f-13f                   # M2: a seeded slice of one SEC 13F data set -> fixtures/us/13f/
  fetch_fixtures.py f-events                # M2: 2 EDGAR daily indexes + submissions + a Form 10 -> fixtures/us/events/
  fetch_fixtures.py f-in                    # M3: NSE/BSE bhavcopy, securities, ASM/GSM, results + shareholding
                                            #     XBRL, PIT, announcements -> fixtures/in/ (patient: NSE blocks bursts)

F-PX stays synthetic (fixtures/px/make_px.py): its one price source, Twelve Data, needs a key.
Needs SEC_USER_AGENT and a network policy that allows the BRIEF §0.2 domains. MOCK_EXTERNALS is ignored here.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.india.securities import NSE_EQUITY_LIST_URL  # noqa: E402
from pipeline.net.http import HttpClient  # noqa: E402
from pipeline.settings import Settings  # noqa: E402
from pipeline.us.universe import SEC_TICKERS_EXCHANGE_URL  # noqa: E402

UNIVERSE_DIR = ROOT / "data" / "universe"
FIXTURES = ROOT / "fixtures"

UNIVERSE_SOURCES = {
    "sec": (SEC_TICKERS_EXCHANGE_URL, "us_tickers_exchange.json"),
    "nse": (NSE_EQUITY_LIST_URL, "nse_equity_list.csv"),
}

# F-US (BRIEF §9): 8 real companies chosen for their calendars: 52/53-week years (AAPL, NVDA), June/May/August
# year ends (MSFT, ORCL, JBL), calendar industrials with backlog/RPO (CAT, PWR), a 2024 spin-off (GEV).
F_US = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "CAT": "0000018230",
    "ORCL": "0001341439",
    "PWR": "0001050915",
    "JBL": "0000898293",
    "GEV": "0001996810",
}
# Forms kept in the trimmed submissions fixture: the filings M2 reads (fundamentals, events, spin-offs).
F_US_FORMS = {
    "10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "10-QT", "8-K", "8-K/A", "NT 10-K", "NT 10-Q",
    "10-12B", "10-12B/A", "EFFECT", "20-F", "40-F",
}  # fmt: skip
SUBMISSION_ARRAYS = ("accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form", "items",
                     "primaryDocument")  # fmt: skip


# F-F4 (BRIEF §9): 10 real Form 4 full submissions (SGML header with ACCEPTANCE-DATETIME + the XML), found with EDGAR
# full-text search. (accession, a CIK on the filing, why it is in the set)
F_F4 = [
    ("0000950170-25-030327", "886744", "GERON insider cluster 2025-03-03: open-market buy (P)"),
    ("0000950170-25-030329", "886744", "GERON insider cluster: open-market buy (P)"),
    ("0000950170-25-030330", "886744", "GERON insider cluster: open-market buy (P)"),
    ("0000784199-25-000043", "784199", "ARTIVION director: two open-market buys (P)"),
    ("0000950170-25-055869", "1697500", "SOLARIS ENERGY: two open-market buys (P)"),
    ("0001524358-25-000052", "1524358", "MARRIOTT VACATIONS director: open-market buy (P)"),
    ("0000002488-24-000104", "2488", "AMD officer: 10b5-1 checkbox, option exercise (derivative M) + sales"),
    ("0001596532-24-000253", "1596532", "ARISTA CEO: 10b5-1 checkbox, sales (S)"),
    ("0001127602-24-017715", "946581", "TAKE-TWO CEO: 10b5-1 checkbox, mixed codes A/D/G/J/S"),
    ("0000006281-22-000181", "6281", "ANALOG DEVICES (2022, before the checkbox): 10b5-1 in footnotes only"),
]


# F-13F (BRIEF §9): a slice of one SEC Form 13F data set (filings 1 Dec 2024 - 28 Feb 2025; period 2024-12-31).
F_13F_URL = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/01dec2024-28feb2025_form13f.zip"
F_13F_ISSUERS = [  # F-US names + capex-desk names + a spread of other US listings, plus ETF/ADR noise
    "APPLE INC", "MICROSOFT CORP", "NVIDIA CORPORATION", "CATERPILLAR INC", "ORACLE CORP", "QUANTA SVCS INC",
    "JABIL INC", "GE VERNOVA INC", "VERTIV HOLDINGS CO", "EATON CORP PLC", "HUBBELL INC", "POWELL INDS INC",
    "CORNING INC", "ARISTA NETWORKS INC", "AMPHENOL CORP NEW", "COHERENT CORP", "LUMENTUM HLDGS INC",
    "CIENA CORP", "MARVELL TECHNOLOGY INC", "MICRON TECHNOLOGY INC", "BROADCOM INC", "ADVANCED MICRO DEVICES INC",
    "EMCOR GROUP INC", "COMFORT SYS USA INC", "MASTEC INC", "STERLING INFRASTRUCTURE INC", "PRIMORIS SVCS CORP",
    "CONSTELLATION ENERGY CORP", "VISTRA CORP", "TALEN ENERGY CORP", "NRG ENERGY INC", "DOMINION ENERGY INC",
    "SOUTHERN CO", "NEXTERA ENERGY INC", "DUKE ENERGY CORP NEW", "EQUINIX INC", "DIGITAL RLTY TR INC",
    "IRON MTN INC DEL", "MODINE MFG CO", "TRANE TECHNOLOGIES PLC", "JOHNSON CTLS INTL PLC", "BLOOM ENERGY CORP",
    "FLUENCE ENERGY INC", "CUMMINS INC", "NVENT ELECTRIC PLC", "WESTERN DIGITAL CORP", "SEAGATE TECHNOLOGY HLDNGS P",
    "APPLIED MATLS INC", "LAM RESEARCH CORP", "KLA CORP", "DELL TECHNOLOGIES INC", "SUPER MICRO COMPUTER INC",
    "HEWLETT PACKARD ENTERPRISE C", "FLEX LTD", "INTEL CORP", "META PLATFORMS INC", "AMAZON COM INC",
    "ALPHABET INC", "GERON CORP", "ARTIVION INC", "MARRIOTT VACATIONS WORLDWIDE",
    "SPDR S&P 500 ETF TR", "TAIWAN SEMICONDUCTOR MFG LTD", "ASML HOLDING N V",
]  # fmt: skip
F_13F_FILERS = 200  # seeded sample of holdings-report filers
F_13F_AMENDMENTS = {"RESTATEMENT": 15, "NEW HOLDINGS": 5}  # seeded sample of amendments (+ their originals)
F_13F_SEED = 13


# F-EVENTS (M2-04): real EDGAR daily indexes and the submissions they point at: Geron's Form 4 cluster (2025-03-03),
# NT 10-K late filings (MRC Global, Ironwood, ADMA), QuidelOrtho's auditor change (8-K item 4.01, 2025-03-04), and
# GE Vernova's Form 10 (parent link for the spin-off).
F_EVENTS_DAYS = ["2025-03-03", "2025-03-04"]
F_EVENTS_CIKS = {"0000886744", "0001906324", "0001439095", "0001446847", "0001368514"}
F_EVENTS_NOISE_ROWS = 25  # first rows of each index kept as unrelated noise
F_EVENTS_FORM10 = "https://www.sec.gov/Archives/edgar/data/1996810/000119312524059354/d542465d1012ba.htm"


def fetch_universe(client: HttpClient, sources: tuple[str, ...] = ("sec", "nse")) -> list[str]:
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url, name in (UNIVERSE_SOURCES[s] for s in sources):
        try:
            (UNIVERSE_DIR / name).write_bytes(client.get_bytes(url))
            print(f"fetched {url} -> data/universe/{name}")
        except Exception as e:  # noqa: BLE001 — report every source, then fail
            errors.append(f"{url}: {type(e).__name__}: {e}")
    return errors


def xbrl_concepts() -> dict[str, set[str]]:
    """namespace -> concepts named in config/signals.yaml xbrl_map (bare names are us-gaap)."""
    cfg = yaml.safe_load((ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {"us-gaap": set(), "dei": set()}
    for alternatives in cfg["xbrl_map"].values():
        if isinstance(alternatives, str):
            continue  # a formula note (ind_as_map style), not a concept list
        for alt in alternatives:
            for c in [alt] if isinstance(alt, str) else alt:
                ns, _, name = c.rpartition(":")
                out[ns or "us-gaap"].add(name)
    return out


def trim_companyfacts(doc: dict[str, Any], keep: dict[str, set[str]]) -> dict[str, Any]:
    """Keep only the mapped concepts; drop long descriptions. Values are untouched (real SEC data)."""
    facts: dict[str, Any] = {}
    for ns, concepts in keep.items():
        for name in sorted(concepts):
            item = (doc.get("facts", {}).get(ns) or {}).get(name)
            if item:
                facts.setdefault(ns, {})[name] = {"label": item.get("label"), "units": item["units"]}
    return {"cik": doc["cik"], "entityName": doc["entityName"], "facts": facts}


def trim_submissions(doc: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge the older-filings pages into `recent` and keep only F_US_FORMS rows and the arrays M2 reads."""
    rows: list[dict[str, Any]] = []
    for block in [doc["filings"]["recent"], *pages]:
        n = len(block["accessionNumber"])
        for i in range(n):
            if block["form"][i] in F_US_FORMS:
                rows.append({k: block[k][i] for k in SUBMISSION_ARRAYS})
    rows.sort(key=lambda r: (r["filingDate"], r["accessionNumber"]), reverse=True)
    recent = {k: [r[k] for r in rows] for k in SUBMISSION_ARRAYS}
    keep = ("cik", "entityType", "sic", "sicDescription", "name", "tickers", "exchanges", "fiscalYearEnd")
    return {**{k: doc.get(k) for k in keep}, "filings": {"recent": recent, "files": []}}


def fetch_f_us(client: HttpClient) -> list[str]:
    out_cf = FIXTURES / "us" / "companyfacts"
    out_sub = FIXTURES / "us" / "submissions"
    out_cf.mkdir(parents=True, exist_ok=True)
    out_sub.mkdir(parents=True, exist_ok=True)
    keep = xbrl_concepts()
    errors: list[str] = []
    for ticker, cik in F_US.items():
        try:
            cf = json.loads(client.get_bytes(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"))
            (out_cf / f"CIK{cik}.json").write_text(
                json.dumps(trim_companyfacts(cf, keep), separators=(",", ":")) + "\n"
            )
            sub = json.loads(client.get_bytes(f"https://data.sec.gov/submissions/CIK{cik}.json"))
            pages = [
                json.loads(client.get_bytes(f"https://data.sec.gov/submissions/{f['name']}"))
                for f in sub["filings"].get("files", [])
            ]
            (out_sub / f"CIK{cik}.json").write_text(
                json.dumps(trim_submissions(sub, pages), separators=(",", ":")) + "\n"
            )
            print(f"fetched F-US {ticker} (CIK {cik}): companyfacts + submissions ({len(pages)} older pages)")
        except Exception as e:  # noqa: BLE001 — report every company, then fail
            errors.append(f"F-US {ticker}: {type(e).__name__}: {e}")
    return errors


def fetch_f_f4(client: HttpClient) -> list[str]:
    out = FIXTURES / "us" / "form4"
    out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for accession, cik, why in F_F4:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}.txt"
        try:
            (out / f"{accession}.txt").write_bytes(client.get_bytes(url))
            print(f"fetched F-F4 {accession}: {why}")
        except Exception as e:  # noqa: BLE001 — report every filing, then fail
            errors.append(f"F-F4 {accession}: {type(e).__name__}: {e}")
    return errors


def fetch_f_13f(client: HttpClient) -> list[str]:
    """Download the data set once and keep a seeded slice in the same TSV format the pipeline reads."""
    import csv
    import io
    import random
    import zipfile

    out = FIXTURES / "us" / "13f"
    out.mkdir(parents=True, exist_ok=True)
    try:
        z = zipfile.ZipFile(io.BytesIO(client.get_bytes(F_13F_URL, timeout=600.0)))
    except Exception as e:  # noqa: BLE001
        return [f"F-13F: {type(e).__name__}: {e}"]

    def table(name: str) -> tuple[list[str], list[dict[str, str]]]:
        reader = csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8"), delimiter="\t")
        return list(reader.fieldnames or []), list(reader)

    issuers = set(F_13F_ISSUERS)
    sub_cols, subs = table("SUBMISSION.tsv")
    cov_cols, covs = table("COVERPAGE.tsv")
    info_cols, _ = table("OTHERMANAGER.tsv")  # header check only
    del info_cols
    # CUSIPs are chosen by their majority issuer name over the whole data set (a few filers mislabel rows, e.g.
    # AbbVie's CUSIP as "APPLE INC"); every sampled filer's rows for those CUSIPs are kept, mislabels included.
    from collections import Counter, defaultdict

    votes: dict[str, Counter[str]] = defaultdict(Counter)
    reader = csv.DictReader(io.TextIOWrapper(z.open("INFOTABLE.tsv"), encoding="utf-8"), delimiter="\t")
    it_cols = list(reader.fieldnames or [])
    for r in reader:
        votes[r["CUSIP"].upper()][r["NAMEOFISSUER"]] += 1
    targets = {c for c, v in votes.items() if v.most_common(1)[0][0] in issuers}
    holdings: dict[str, list[dict[str, str]]] = {}
    for r in csv.DictReader(io.TextIOWrapper(z.open("INFOTABLE.tsv"), encoding="utf-8"), delimiter="\t"):
        if r["CUSIP"].upper() in targets:
            holdings.setdefault(r["ACCESSION_NUMBER"], []).append(r)
    cover = {c["ACCESSION_NUMBER"]: c for c in covs}
    hr = [s for s in subs if s["SUBMISSIONTYPE"] == "13F-HR" and s["ACCESSION_NUMBER"] in holdings]
    amended = [s for s in subs if s["SUBMISSIONTYPE"] == "13F-HR/A" and s["ACCESSION_NUMBER"] in holdings]
    rng = random.Random(F_13F_SEED)  # noqa: S311 — reproducible fixture sampling, not security
    chosen = {s["ACCESSION_NUMBER"] for s in rng.sample(sorted(hr, key=lambda s: s["ACCESSION_NUMBER"]), F_13F_FILERS)}
    picked: list[dict[str, str]] = []
    for kind, n in F_13F_AMENDMENTS.items():
        pool = sorted((s for s in amended if cover[s["ACCESSION_NUMBER"]]["AMENDMENTTYPE"] == kind),
                      key=lambda s: s["ACCESSION_NUMBER"])  # fmt: skip
        picked += rng.sample(pool, min(n, len(pool)))
    amend_ciks = {s["CIK"] for s in picked}
    chosen |= {s["ACCESSION_NUMBER"] for s in picked}
    chosen |= {s["ACCESSION_NUMBER"] for s in hr if s["CIK"] in amend_ciks}  # the originals the amendments amend
    notices = [s for s in subs if s["SUBMISSIONTYPE"] == "13F-NT"][:5]
    chosen |= {s["ACCESSION_NUMBER"] for s in notices}

    def write(name: str, cols: list[str], rows: list[dict[str, str]]) -> None:
        with (out / name).open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    write("SUBMISSION.tsv", sub_cols, sorted((s for s in subs if s["ACCESSION_NUMBER"] in chosen),
                                             key=lambda s: s["ACCESSION_NUMBER"]))  # fmt: skip
    write("COVERPAGE.tsv", cov_cols, [cover[a] for a in sorted(chosen) if a in cover])
    write("INFOTABLE.tsv", it_cols, [r for a in sorted(chosen) for r in holdings.get(a, [])])
    (out / "window.json").write_text(json.dumps({"source": F_13F_URL, "filed_through": "2025-02-28"}) + "\n")
    print(f"F-13F slice: {len(chosen)} filings, {sum(len(holdings.get(a, [])) for a in chosen)} holdings rows")
    return []


def fetch_f_events(client: HttpClient) -> list[str]:
    out = FIXTURES / "us" / "events"
    out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for day in F_EVENTS_DAYS:
        y, m, d = day.split("-")
        q = (int(m) - 1) // 3 + 1
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/master.{y}{m}{d}.idx"
        try:
            lines = client.get_bytes(url).decode("latin-1").splitlines()
        except Exception as e:  # noqa: BLE001
            errors.append(f"F-EVENTS {url}: {type(e).__name__}: {e}")
            continue
        head = next(i for i, ln in enumerate(lines) if ln.startswith("-----")) + 1
        body = lines[head:]
        keep = body[:F_EVENTS_NOISE_ROWS] + [ln for ln in body if ln.split("|")[0].zfill(10) in F_EVENTS_CIKS]
        (out / f"master.{y}{m}{d}.idx").write_text("\n".join(lines[:head] + list(dict.fromkeys(keep))) + "\n")
    for cik in sorted(F_EVENTS_CIKS - {"0000886744"}):
        try:
            sub = json.loads(client.get_bytes(f"https://data.sec.gov/submissions/CIK{cik}.json"))
            trimmed = trim_submissions(sub, [])
            recent = trimmed["filings"]["recent"]
            idx = [i for i, fd in enumerate(recent["filingDate"]) if "2024-10-01" <= fd <= "2025-06-30"]
            trimmed["filings"]["recent"] = {k: [v[i] for i in idx] for k, v in recent.items()}
            (out / f"CIK{cik}.json").write_text(json.dumps(trimmed, separators=(",", ":")) + "\n")
        except Exception as e:  # noqa: BLE001
            errors.append(f"F-EVENTS submissions {cik}: {type(e).__name__}: {e}")
    try:
        (out / "gev_form10.htm").write_bytes(client.get_bytes(F_EVENTS_FORM10))
    except Exception as e:  # noqa: BLE001
        errors.append(f"F-EVENTS form 10: {type(e).__name__}: {e}")
    print(f"F-EVENTS: {len(F_EVENTS_DAYS)} daily indexes, {len(F_EVENTS_CIKS) - 1} submissions, 1 Form 10")
    return errors


# F-IN (BRIEF §9, §8 M3): real NSE/BSE files. KEI Industries (capex desk: cables) is the results company: Q2, Q3 and
# Q4 of FY2026 consolidated (half-yearly balance sheet and cash flow in Q2/Q4), plus a standalone Q3 (the basis rule)
# and the FY2027 Q1 standalone original + revision (a restatement). Shareholding: KEI plus two companies whose
# promoters pledge shares. Files already present are kept (the fetch is resumable).
F_IN_ARCH = "https://nsearchives.nseindia.com/corporate/xbrl"
F_IN_FILES: list[tuple[str, str]] = [
    ("bhavcopy/BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip",
     "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip"),
    ("bhavcopy/BhavCopy_BSE_CM_0_0_0_20260605_F_0000.CSV",
     "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_20260605_F_0000.CSV"),
    ("securities/EQUITY_L.csv", "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"),
    ("securities/asm.json", "https://www.nseindia.com/api/reportASM"),
    ("securities/gsm.json", "https://www.nseindia.com/api/reportGSM"),
    ("results/index_KEI.json",
     "https://www.nseindia.com/api/integrated-filing-results?index=equities&type=Integrated%20Filing-%20Financials&symbol=KEI"),
    ("results/KEI_FY2026Q2_consolidated.xml", f"{F_IN_ARCH}/INTEGRATED_FILING_INDAS_1549479_15102025075915_WEB.xml"),
    ("results/KEI_FY2026Q3_consolidated.xml", f"{F_IN_ARCH}/INTEGRATED_FILING_INDAS_1607504_21012026062530_WEB.xml"),
    ("results/KEI_FY2026Q4_consolidated.xml", f"{F_IN_ARCH}/INTEGRATED_FILING_INDAS_1663459_04052026092025_WEB.xml"),
    ("results/KEI_FY2026Q3_standalone.xml", f"{F_IN_ARCH}/INTEGRATED_FILING_INDAS_1607503_21012026062525_WEB.xml"),
    ("results/KEI_FY2027Q1_standalone.xml", f"{F_IN_ARCH}/INTEGRATED_FILING_INDAS_1707263_03082026084835_WEB.xml"),
    ("results/KEI_FY2027Q1_standalone_revision.xml",
     f"{F_IN_ARCH}/INTEGRATED_FILING_INDAS_1707294_03082026102024_WEB.xml"),
    ("results/legacy_VSTTILLERS_FY2025Q3.xml", f"{F_IN_ARCH}/INDAS_121277_1705282_30072026051753.xml"),
    # the history loader (pipeline/india/history.py; docs/SPEC_ISSUES.md 55): KEI's legacy listing (trimmed to its
    # quarters from 2022 plus its oldest row), a legacy quarter whose file never defines the contexts its facts use
    # (December 2022), two legacy half years and a legacy year (their year-to-date column is stamped with the
    # quarter's dates), the integrated FY2025 Q4 whose H2 needs the legacy H1, and KEI's own shareholding listing
    ("results/legacy_index_KEI.json",
     "https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly&symbol=KEI"),
    ("results/legacy_KEI_FY2023Q3_consolidated.xml", f"{F_IN_ARCH}/INDAS_87681_777741_23012023063403_WEB.xml"),
    ("results/legacy_KEI_FY2024Q2_consolidated.xml", f"{F_IN_ARCH}/INDAS_98422_973421_01112023043110.xml"),
    ("results/legacy_KEI_FY2024Q4_consolidated.xml", f"{F_IN_ARCH}/INDAS_105215_1114525_03052024032358.xml"),
    ("results/legacy_KEI_FY2025Q2_consolidated.xml", f"{F_IN_ARCH}/INDAS_112803_1272446_16102024040014.xml"),
    ("results/KEI_FY2025Q4_consolidated.xml", f"{F_IN_ARCH}/INTEGRATED_FILING_INDAS_1432738_06052025093549_WEB.xml"),
    ("shareholding/index_KEI.json",
     "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=KEI"),
    ("shareholding/index.json", "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities"),
    ("shareholding/SHP_KEI_2026-06-30.xml", f"{F_IN_ARCH}/SHP_1696739_20072026031837_WEB.xml"),
    ("shareholding/SHP_JSWSTEEL_2026-06-30.xml", f"{F_IN_ARCH}/SHP_1698632_21072026062045_WEB.xml"),
    ("shareholding/SHP_JPPOWER_2026-06-30.xml", f"{F_IN_ARCH}/SHP_1691416_13072026035716_WEB.xml"),
    ("pit/pit.json", "https://www.nseindia.com/api/corporates-pit-gg?index=equities"),  # the page's activeApiName
    ("announcements/announcements.json", "https://www.nseindia.com/api/corporate-announcements?index=equities"),
    # the pages' "Download (.csv)" files, the manual import's input (review F4 on M3)
    ("announcements/announcements_2026-09-19.csv",
     "https://www.nseindia.com/api/corporate-announcements?index=equities&from_date=19-09-2026&to_date=19-09-2026"
     "&csv=true"),
    ("shareholding/shareholding_page.csv",
     "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&csv=true"),
    *((f"pit/disclosures/{u.rsplit('/', 1)[-1]}", u) for u in (  # every 170th disclosure of the PIT index
        f"{F_IN_ARCH}/IT_22933_WebXMLFile_20260925_132011105.xml",  # SINCLAIR
        f"{F_IN_ARCH}/IT_23163_WebXMLFile_20260919_124927843.xml",  # AQYLON
        f"{F_IN_ARCH}/IT_1496_WebXMLFile_20260911_171905572.xml",  # ELECTHERM
        f"{F_IN_ARCH}/IT_20784_WebXMLFile_20260907_121156624.xml",  # CSLFINANCE
        f"{F_IN_ARCH}/IT_3067_WebXMLFile_20260901_172346283.xml",  # THANGAMAYL
        f"{F_IN_ARCH}/IT_13498_WebXMLFile_20260826_153544367.xml",  # BHAGERIA
        f"{F_IN_ARCH}/IT_17593_WebXMLFile_20260819_213411802.xml",  # 360ONE
        f"{F_IN_ARCH}/IT_14236_WebXMLFile_20260812_153243430.xml",  # GNA
        f"{F_IN_ARCH}/PIT_530475_2872026173846_IT_WebXMLFile_20260728_173852777.xml",  # TINNARUBR
        f"{F_IN_ARCH}/PIT_532507_172026172031_IT_WebXMLFile_20260701_172036496.xml",  # BAGFILMS
        f"{F_IN_ARCH}/PIT_540724_2662026144622_IT_WebXMLFile_20260626_144807138.xml",  # DIAMONDYD
        f"{F_IN_ARCH}/PIT_543513_2062026173325_IT_WebXMLFile_20260620_173348364.xml",  # UMAEXPORTS
        f"{F_IN_ARCH}/PIT_507910_166202615653_IT_WebXMLFile_20260616_150659137.xml",  # FIBERWEB
        f"{F_IN_ARCH}/PIT_532809_1062026161554_IT_WebXMLFile_20260610_161822642.xml",  # FSL
        f"{F_IN_ARCH}/PIT_524774_462026163113_IT_WebXMLFile_20260604_163257665.xml",  # NGLFINE
        f"{F_IN_ARCH}/PIT_531120_2852026122358_IT_WebXMLFile_20260528_122404596.xml",  # PATELENG
        f"{F_IN_ARCH}/PIT_539524_185202615324_IT_WebXMLFile_20260518_153248238.xml",  # LALPATHLAB
    )),
]  # fmt: skip
F_IN_KEEP_SHP = {"KEI", "JSWSTEEL", "JPPOWER"}  # the shareholding listing is trimmed to these
# the shareholding page's CSV is trimmed to these companies plus every 100th row (it has names, not symbols)
F_IN_KEEP_SHP_NAMES = {"KEI Industries Limited", "JSW Steel Limited", "Jaiprakash Power Ventures Limited",
                       "Bhageria Industries Limited"}  # fmt: skip


def trim_shareholding_csv(body: bytes) -> bytes:
    lines = body.decode("utf-8-sig").splitlines(keepends=True)
    keep = [
        x for n, x in enumerate(lines[1:], 1) if n % 100 == 0 or x.split('","')[0].strip('"') in F_IN_KEEP_SHP_NAMES
    ]
    return ("\ufeff" + lines[0] + "".join(keep)).encode()


def trim_legacy_listing(body: bytes) -> bytes:
    """NSE's legacy results listing for one company, every quarter back to 2005: its quarters from 2022 on and its
    oldest row (no XBRL, no dissemination time)."""
    rows = json.loads(body)
    keep = [r for r in rows if str(r.get("toDate") or "")[-4:] >= "2022"] + rows[-1:]
    return (json.dumps(keep, indent=1) + "\n").encode()


def fetch_f_in(client: HttpClient, cooldown_s: float = 600.0, rounds: int = 4) -> list[str]:
    import time

    from pipeline.net.bse import BseClient
    from pipeline.net.nse import NseBlocked, NseClient

    out = FIXTURES / "in"
    todo = [(out / rel, url) for rel, url in F_IN_FILES if not (out / rel).exists()]
    errors: list[str] = []
    for n in range(rounds):
        nse, bse, failed = NseClient(client, backoff=(30.0, 90.0)), BseClient(client), []
        for dest, url in todo:
            try:
                body = bse.get(url) if "bseindia.com" in url else nse.get(url)
            except (NseBlocked, Exception) as e:  # noqa: BLE001 — reported, retried next round
                failed.append((dest, url))
                errors.append(f"{dest.relative_to(ROOT)}: {type(e).__name__}: {e}")
                continue
            if dest.name == "index.json" and dest.parent.name == "shareholding":
                rows = [r for r in json.loads(body) if r.get("symbol") in F_IN_KEEP_SHP]
                body = (json.dumps(rows, indent=1) + "\n").encode()
            if dest.name == "shareholding_page.csv":
                body = trim_shareholding_csv(body)
            if dest.name == "legacy_index_KEI.json":
                body = trim_legacy_listing(body)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            print(f"F-IN {dest.relative_to(ROOT)}: {len(body):,} bytes")
        todo = failed
        if not todo:
            return []
        if n < rounds - 1:
            print(f"F-IN: {len(todo)} files blocked; cooling down {cooldown_s:.0f}s (round {n + 1}/{rounds})")
            errors = []
            time.sleep(cooldown_s)
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["universe", "f-us", "f-f4", "f-13f", "f-events", "f-in"])
    ap.add_argument("--source", choices=["all", *UNIVERSE_SOURCES], default="all")
    a = ap.parse_args(argv)
    settings = dataclasses.replace(Settings.from_env(), mock_externals=False)
    client = HttpClient(settings)
    if a.what == "universe":
        sources = tuple(UNIVERSE_SOURCES) if a.source == "all" else (a.source,)
        errors = fetch_universe(client, sources)
    elif a.what == "f-us":
        errors = fetch_f_us(client)
    elif a.what == "f-f4":
        errors = fetch_f_f4(client)
    elif a.what == "f-13f":
        errors = fetch_f_13f(client)
    elif a.what == "f-in":
        errors = fetch_f_in(client)
    else:
        errors = fetch_f_events(client)
    for e in errors:
        print(f"FAILED {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

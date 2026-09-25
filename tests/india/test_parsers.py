"""India parsers on F-IN (BRIEF §4.3, §8 M3-01..M3-03): UDiFF bhavcopy, results XBRL -> fundamentals rows
(half-yearly balance sheet and cash flow), shareholding + pledge %, surveillance lists, announcements."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from pipeline.india import announcements, bhavcopy
from pipeline.india.results_xbrl import Filed, build_rows, load_ind_as_map, parse_results
from pipeline.india.securities import parse_asm, parse_equity_list, parse_gsm
from pipeline.india.shareholding import parse_listing, parse_shareholding
from pipeline.india.xbrl import XbrlError, parse_instance

FIN = Path(__file__).resolve().parents[2] / "fixtures" / "in"
IND_AS = load_ind_as_map()


# ---------------------------------------------------------------- M3-01 bhavcopy


def nse_raw() -> bytes:
    return (FIN / "bhavcopy" / "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip").read_bytes()


def test_nse_udiff_bhavcopy() -> None:
    b = bhavcopy.parse(nse_raw())
    assert (b.source, b.trade_date, len(b.rows), b.warnings) == ("NSE", date(2026, 6, 5), 2443, [])
    kei = next(r for r in b.rows if r.symbol == "KEI")
    assert (kei.isin, kei.close, kei.volume, kei.series) == ("INE878B01027", D("5335.50"), 203971, "EQ")
    assert {r.series for r in b.rows} == {"EQ"} and b.skipped == 974  # SM, BE, GB, … and non-final sessions


def _csv_text() -> str:
    with zipfile.ZipFile(io.BytesIO(nse_raw())) as z:
        return z.read(z.namelist()[0]).decode("utf-8")


def test_unknown_columns_are_a_warning_and_columns_are_found_by_name() -> None:
    rows = list(csv.reader(io.StringIO(_csv_text())))
    header, body = rows[0], rows[1:50]
    # a new column, and the known ones in a different order: parsed by name, never by position
    order = list(reversed(range(len(header))))
    shuffled = [[*(r[i] for i in order), "x"] for r in [header, *body]]
    shuffled[0][-1] = "NewColumn2027"
    text = "\n".join(",".join(r) for r in shuffled) + "\n"
    b = bhavcopy.parse(text.encode())
    assert b.warnings == ["unknown columns ignored: ['NewColumn2027']"]
    assert [(r.symbol, r.close) for r in b.rows] == [
        (r.symbol, r.close)
        for r in bhavcopy.parse(nse_raw()).rows
        if r.symbol in {x[header.index("TckrSymb")] for x in body}
    ]


def test_missing_required_column_is_an_error() -> None:
    text = _csv_text().replace("ClsPric", "ClosePrice", 1)
    with pytest.raises(bhavcopy.BhavcopySchemaError, match="ClsPric"):
        bhavcopy.parse(text.encode())


def test_bse_bhavcopy_and_its_missing_file_page() -> None:
    raw = (FIN / "bhavcopy" / "BhavCopy_BSE_CM_0_0_0_20260605_F_0000.CSV").read_bytes()
    b = bhavcopy.parse(raw, series=None)
    assert (b.source, b.trade_date, len(b.rows)) == ("BSE", date(2026, 6, 5), 4823)
    nse_isins = {r.isin for r in bhavcopy.parse(nse_raw()).rows}
    assert sum(r.isin in nse_isins for r in b.rows) == 2225  # BSE covers ~91% of the NSE EQ universe by ISIN
    assert bhavcopy.looks_like_bhavcopy(raw) and bhavcopy.looks_like_bhavcopy(nse_raw())
    assert not bhavcopy.looks_like_bhavcopy(b"<!DOCTYPE html><html><head><title>BSE</title>")
    assert bhavcopy.week_days_back(date(2026, 6, 5)) == [date(2026, 6, d) for d in (5, 4, 3, 2, 1)]


# ---------------------------------------------------------------- M3-02 results XBRL


def filed(name: str) -> Filed:
    listing = json.loads((FIN / "results" / "index_KEI.json").read_text(encoding="utf-8"))["data"]
    raw = (FIN / "results" / name).read_bytes()
    r = parse_results(raw, IND_AS)
    entry = next(
        e
        for e in listing
        if e["qe_Date"] == r.period_end.strftime("%d-%b-%Y").upper()
        and e["consolidated"].lower() == r.basis
        and ("revision" in name) == (e["type_Sub"] == "Revision")
    )
    return Filed(r, announcements.ist_to_utc(entry["creation_Date"]), entry["xbrl"])


def expected_rows() -> list[dict[str, str]]:
    with (FIN / "results" / "expected_KEI.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_kei_results_equal_the_expected_rows() -> None:
    build = build_rows([filed(f"KEI_FY2026Q{q}_consolidated.xml") for q in (4, 2, 3)])  # any order
    assert build.issues == [] and build.ignored == []
    got = [{"period_end": r.period_end.isoformat(), "fiscal_label": r.fiscal_label, "filed_at": r.filed_at.isoformat(),
            **{c: "" if v is None else str(v) for c, v in r.values.items()}} for r in build.rows]  # fmt: skip
    for g, e in zip(got, expected_rows(), strict=True):
        assert {k: g.get(k, "") for k in e} == e


def test_half_yearly_balance_sheet_and_cash_flow() -> None:
    rows = {
        r.fiscal_label: r.values
        for r in build_rows([filed(f"KEI_FY2026Q{q}_consolidated.xml") for q in (2, 3, 4)]).rows
    }
    assert all(rows["FY2026Q3"][c] is None for c in ("total_assets", "cash", "equity", "total_debt", "cfo", "capex"))
    assert rows["FY2026Q2"]["cfo"] == D(3828990000)  # H1 (April-September)
    assert rows["FY2026Q4"]["cfo"] == D(8399540000) - D(3828990000)  # H2 = FY - H1
    assert rows["FY2026Q2"]["cfo"] + rows["FY2026Q4"]["cfo"] == D(8399540000)  # TTM CFO = H1 + H2
    alone = build_rows([filed("KEI_FY2026Q4_consolidated.xml")])  # no H1 known: H2 unknown, never the FY total
    assert alone.rows[0].values["cfo"] is None and alone.rows[0].values["total_assets"] == D(89559780000)


def test_consolidated_wins_and_revisions_are_versions() -> None:
    q3c, q3s = filed("KEI_FY2026Q3_consolidated.xml"), filed("KEI_FY2026Q3_standalone.xml")
    assert (q3c.filed_at - q3s.filed_at).seconds == 6  # KEI filed standalone first, consolidated 6 s later
    b = build_rows([q3c, q3s])
    assert [r.basis for r in b.rows] == ["standalone"] and b.ignored == []  # same numbers: no second version
    late = replace(q3s, filed_at=q3c.filed_at.replace(minute=59))  # a standalone filing after the consolidated one
    b = build_rows([q3c, replace(late, results=replace(late.results, pl={**late.results.pl, "revenue": D(1)}))])
    assert [(r.basis, r.values["revenue"]) for r in b.rows] == [("consolidated", D(29547040000))]
    assert len(b.ignored) == 1 and "consolidated already filed" in b.ignored[0]
    orig, rev = filed("KEI_FY2027Q1_standalone.xml"), filed("KEI_FY2027Q1_standalone_revision.xml")
    assert rev.filed_at > orig.filed_at
    assert len(build_rows([orig, rev]).rows) == 1  # the revision changed no number: no new version
    changed = replace(rev, results=replace(rev.results, pl={**rev.results.pl, "revenue": D(31853420001)}))
    versions = build_rows([orig, changed]).rows
    assert [(r.filed_at, r.values["revenue"]) for r in versions] == [
        (orig.filed_at, D(31853420000)), (rev.filed_at, D(31853420001))]  # fmt: skip
    mixed = build_rows([replace(filed("KEI_FY2026Q2_consolidated.xml"),
                                results=replace(filed("KEI_FY2026Q2_consolidated.xml").results, basis="standalone")),
                        filed("KEI_FY2026Q4_consolidated.xml")])  # fmt: skip
    q4 = next(r for r in mixed.rows if r.fiscal_label == "FY2026Q4")
    assert q4.values["cfo"] is None and "H2 cash flow left null" in mixed.issues[0]


def test_legacy_taxonomy_and_metadata() -> None:
    r = parse_results((FIN / "results" / "legacy_VSTTILLERS_FY2025Q3.xml").read_bytes(), IND_AS)
    assert (r.symbol, r.fiscal_label, r.basis, r.audited) == ("VSTTILLERS", "FY2025Q3", "consolidated", False)
    assert r.pl["revenue"] == D("2191000000.00") and r.shares_outstanding == D(8640000)
    kei = parse_results((FIN / "results" / "KEI_FY2026Q4_consolidated.xml").read_bytes(), IND_AS)
    assert (kei.isin, kei.audited, kei.shares_outstanding) == ("INE878B01027", True, D(95600000))


def test_unsafe_or_foreign_xml_is_refused() -> None:
    with pytest.raises(XbrlError, match="DTD"):
        parse_instance(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><xbrli:xbrl/>')
    with pytest.raises(XbrlError, match="not an XBRL instance"):
        parse_instance(b"<html><body>Access Denied</body></html>")


# ---------------------------------------------------------------- M3-03 shareholding


@pytest.mark.parametrize(
    ("symbol", "promoter", "pledged", "fii", "dii", "inst"),
    [
        ("KEI", "35.0000", "0.0000", "27.3200", "25.9000", "53.2200"),
        ("JSWSTEEL", "44.2900", "11.6000", "10.9100", "11.4900", "37.4100"),  # JFE's strategic stake is not FPI
        ("JPPOWER", "24.0000", "72.9900", "6.7500", "11.1600", "17.9200"),  # R5: pledge ≥ 20% of promoter holding
    ],
)
def test_shareholding_and_pledge(symbol: str, promoter: str, pledged: str, fii: str, dii: str, inst: str) -> None:
    s = parse_shareholding((FIN / "shareholding" / f"SHP_{symbol}_2026-06-30.xml").read_bytes())
    assert (s.symbol, s.quarter_end) == (symbol, date(2026, 6, 30))
    assert (s.promoter_pct, s.promoter_pledged_pct, s.fii_pct, s.dii_pct, s.inst_pct) == (
        D(promoter), D(pledged), D(fii), D(dii), D(inst))  # fmt: skip


def test_shareholding_counts_and_listing() -> None:
    jsw = parse_shareholding((FIN / "shareholding" / "SHP_JSWSTEEL_2026-06-30.xml").read_bytes())
    assert (jsw.total_shares, jsw.promoter_shares, jsw.pledged_shares) == (D(2445453966), D(1083203750), D(125650440))
    assert parse_shareholding((FIN / "shareholding" / "SHP_KEI_2026-06-30.xml").read_bytes()).pledged_shares == 0
    assert jsw.pledged_shares is not None and jsw.promoter_shares and jsw.promoter_pledged_pct is not None
    assert abs(jsw.pledged_shares / jsw.promoter_shares * 100 - jsw.promoter_pledged_pct) < D("0.01")
    listing = {x.symbol: x for x in parse_listing((FIN / "shareholding" / "index.json").read_bytes())}
    assert listing["KEI"].filed_at == datetime(2026, 7, 20, 9, 48, 41, tzinfo=UTC)  # 15:18:41 IST
    assert listing["KEI"].quarter_end == date(2026, 6, 30) and not listing["KEI"].revised


# ---------------------------------------------------------------- surveillance, universe, announcements


def test_surveillance_lists_and_universe() -> None:
    asm = parse_asm((FIN / "securities" / "asm.json").read_bytes())
    gsm = parse_gsm((FIN / "securities" / "gsm.json").read_bytes())
    assert (len(asm), len(gsm)) == (215, 77)
    assert {a.measure for a in asm} == {"ASM long-term", "ASM short-term"} and {g.measure for g in gsm} == {"GSM"}
    assert asm[0].reason == "surveillance: ASM long-term stage Stage I"
    eq = parse_equity_list((FIN / "securities" / "EQUITY_L.csv").read_bytes())
    assert len(eq) == 2317 and len({x.symbol for x in asm + gsm} & {x.symbol for x in eq}) == 188


def test_announcements() -> None:
    a = announcements.parse((FIN / "announcements" / "announcements.json").read_bytes())
    assert len(a) == 20
    first = a[0]
    assert (first.symbol, first.category, first.event_date) == ("NITCO", "Trading Window", date(2026, 9, 25))
    assert first.filed_at == datetime(2026, 9, 25, 7, 42, 34, tzinfo=UTC)  # 13:12:34 IST dissemination
    assert first.pdf_url is not None and first.pdf_url.startswith("https://nsearchives.nseindia.com/corporate/")
    assert announcements.api_path(date(2026, 9, 24), date(2026, 9, 25)).endswith(
        "from_date=24-09-2026&to_date=25-09-2026")  # fmt: skip

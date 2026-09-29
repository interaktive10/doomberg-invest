"""13F holder counts on F-13F (BRIEF §4.2, §8 M2-05): counts equal the independently derived expected values;
CUSIP -> company mapping >= 90% on the hand-reviewed sample, with no wrong matches."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path

from pipeline.us.names import non_common, normalize_name
from pipeline.us.thirteenf import (
    DataSet,
    company_holder_counts,
    dataset_url,
    holders_by_cusip,
    issuer_names,
    main_period,
    map_cusips,
    read_dataset,
    read_dataset_zip,
    windows_before,
)

ROOT = Path(__file__).resolve().parents[2]
F13 = ROOT / "fixtures" / "us" / "13f"


def fixture() -> DataSet:
    window = json.loads((F13 / "window.json").read_text(encoding="utf-8"))
    with (F13 / "SUBMISSION.tsv").open(encoding="utf-8") as s, (F13 / "COVERPAGE.tsv").open(encoding="utf-8") as c, \
            (F13 / "INFOTABLE.tsv").open(encoding="utf-8") as i:  # fmt: skip
        return read_dataset(s, c, i, date.fromisoformat(window["filed_through"]))


def universe_names() -> dict[str, str]:
    snap = json.loads((ROOT / "data" / "universe" / "us_tickers_exchange.json").read_text(encoding="utf-8"))
    i, n = snap["fields"].index("cik"), snap["fields"].index("name")
    return {str(r[i]).zfill(10): r[n] for r in snap["data"]}


def test_counts_equal_expected() -> None:
    ds = fixture()
    assert main_period(ds) == date(2024, 12, 31)
    assert ds.available_at == datetime(2025, 3, 1, tzinfo=UTC)  # the window closes 2025-02-28
    got = {c: len(f) for c, f in holders_by_cusip(ds, date(2024, 12, 31)).items()}
    with (F13 / "expected_counts.csv").open(encoding="utf-8") as fh:
        expected = {r["cusip"]: int(r["holders"]) for r in csv.DictReader(fh)}
    assert got == expected


def test_cusip_mapping_on_the_reviewed_sample() -> None:
    ds = fixture()
    mapping = map_cusips(issuer_names(ds), universe_names())
    with (F13 / "expected_mapping.csv").open(encoding="utf-8") as fh:
        expected = {r["cusip"]: r["cik"] for r in csv.DictReader(fh)}
    right = sum(mapping.cusip_to_cik.get(c) == cik for c, cik in expected.items())
    wrong = {
        c: mapping.cusip_to_cik[c] for c, cik in expected.items() if mapping.cusip_to_cik.get(c) not in (None, cik)
    }
    assert right / len(expected) >= 0.90 and wrong == {}
    assert "Y0486S104" in mapping.unmapped  # a mislabelled CUSIP ("TETRA TECHNOLOGIES INC D") is logged, not forced


def test_overrides_win_and_share_classes_are_one_company() -> None:
    ds = fixture()
    names = universe_names()
    mapping = map_cusips(issuer_names(ds), names, overrides={"Y0486S104": "1730168"})
    assert mapping.cusip_to_cik["Y0486S104"] == "0001730168" and "Y0486S104" not in mapping.unmapped
    holders = holders_by_cusip(ds, date(2024, 12, 31))
    counts = company_holder_counts(holders, mapping)
    alphabet = holders["02079K107"] | holders["02079K305"]  # class C and class A
    assert counts["0001652044"] == len(alphabet) < len(holders["02079K107"]) + len(holders["02079K305"])


def _tsv(header: list[str], rows: list[list[str]]) -> io.StringIO:
    return io.StringIO("\n".join("\t".join(r) for r in [header, *rows]) + "\n")


SUB_H = ["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"]
COV_H = ["ACCESSION_NUMBER", "REPORTCALENDARORQUARTER", "ISAMENDMENT", "AMENDMENTNO", "AMENDMENTTYPE", "REPORTTYPE"]
INF_H = ["ACCESSION_NUMBER", "INFOTABLE_SK", "NAMEOFISSUER", "TITLEOFCLASS", "CUSIP", "VALUE", "SSHPRNAMT",
         "SSHPRNAMTTYPE", "PUTCALL"]  # fmt: skip
HR, NT, P = "13F HOLDINGS REPORT", "13F NOTICE", "31-DEC-2024"


def test_amendments_notices_and_non_common_rows() -> None:
    sub = _tsv(SUB_H, [
        ["a1", "10-FEB-2025", "13F-HR", "1", P], ["a2", "20-FEB-2025", "13F-HR/A", "1", P],  # restated
        ["b1", "10-FEB-2025", "13F-HR", "2", P], ["b2", "21-FEB-2025", "13F-HR/A", "2", P],  # new holdings added
        ["c1", "11-FEB-2025", "13F-NT", "3", P],  # notice: holds nothing
        ["d1", "12-FEB-2025", "13F-HR", "4", "30-SEP-2024"],  # another period
    ])  # fmt: skip
    cov = _tsv(COV_H, [
        ["a1", P, "", "", "", HR], ["a2", P, "Y", "1", "RESTATEMENT", HR], ["b1", P, "", "", "", HR],
        ["b2", P, "Y", "1", "NEW HOLDINGS", HR], ["c1", P, "", "", "", NT], ["d1", P, "", "", "", HR],
    ])  # fmt: skip
    inf = _tsv(INF_H, [
        ["a1", "1", "OLD CO", "COM", "111111101", "1", "1", "SH", ""],
        ["a2", "2", "NEW CO", "COM", "222222102", "1", "1", "SH", ""],
        ["b1", "3", "OLD CO", "COM", "111111101", "1", "1", "SH", ""],
        ["b2", "4", "THIRD CO", "COM", "333333103", "1", "1", "SH", ""],
        ["b1", "5", "OLD CO", "COM", "111111101", "1", "1", "SH", "Call"],  # option position on the stock
        ["b1", "6", "OLD CO", "NOTE 2.5% 2030", "111111AB1", "1", "1", "PRN", ""],  # debt
        ["b1", "7", "OLD CO", "PFD SER A", "111111200", "1", "1", "SH", ""],  # preferred
        ["b1", "8", "PIPELINE PARTNERS", "COM UNIT LTD PARTN", "444444104", "1", "1", "SH", ""],  # MLP common units
        ["c1", "9", "OLD CO", "COM", "111111101", "1", "1", "SH", ""],
        ["d1", "10", "OLD CO", "COM", "111111101", "1", "1", "SH", ""],
    ])  # fmt: skip
    ds = read_dataset(sub, cov, inf, date(2025, 2, 28))
    assert ds.skipped_rows == 3
    holders = holders_by_cusip(ds, date(2024, 12, 31))
    assert holders == {"111111101": {"0000000002"}, "222222102": {"0000000001"}, "333333103": {"0000000002"},
                       "444444104": {"0000000002"}}  # fmt: skip


def test_class_titles_and_name_normalization() -> None:
    assert [non_common(t) for t in ("COM", "CL A", "COM UNIT LTD PARTN", "SHS", "COM NEW")] == [False] * 5
    assert all(non_common(t) for t in ("PFD SER A", "UNIT 06/01/2027", "*W EXP 01/01/202", "OPT", "NOTE 2% 3/1"))
    assert normalize_name("ASML HOLDING N V") == normalize_name("ASML Holding N.V.") == "ASML HOLDING"
    assert normalize_name("QUANTA SVCS INC") == normalize_name("QUANTA SERVICES, INC.") == "QUANTA SERVICES"
    assert normalize_name("Procter & Gamble Co/The") == "PROCTER AND GAMBLE"


def test_data_set_windows_and_urls(tmp_path: Path) -> None:
    assert windows_before(date(2025, 4, 20), 3) == [
        (date(2024, 12, 1), date(2025, 2, 28)), (date(2024, 9, 1), date(2024, 11, 30)),
        (date(2024, 6, 1), date(2024, 8, 31))]  # fmt: skip
    assert windows_before(date(2025, 3, 10))[0] == (date(2024, 9, 1), date(2024, 11, 30))  # Dec-Feb not out yet
    assert windows_before(date(2024, 3, 21))[0] == (date(2023, 12, 1), date(2024, 2, 29))  # leap year
    window = json.loads((F13 / "window.json").read_text(encoding="utf-8"))
    assert dataset_url(date(2024, 12, 1), date(2025, 2, 28)) == window["source"]
    import zipfile

    z = tmp_path / "ds.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for name in ("SUBMISSION.tsv", "COVERPAGE.tsv", "INFOTABLE.tsv"):
            zf.write(F13 / name, f"01dec2024-28feb2025_form13f/{name}")  # members may sit in a folder
    ds = read_dataset_zip(z, date(2025, 2, 28))
    assert len(ds.filings) == len(fixture().filings) and ds.skipped_rows == fixture().skipped_rows

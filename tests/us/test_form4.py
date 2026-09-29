"""Form 4 parsing on F-F4 (BRIEF §4.2, §8 M2-03): code P only, `planned` via the checkbox and via a footnote,
derivatives excluded."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from pipeline.us.form4 import Form4, Form4Error, header_acceptance, parse_submission, parse_xml

F4 = Path(__file__).resolve().parents[2] / "fixtures" / "us" / "form4"


def load(name: str, synthetic: bool = False) -> Form4:
    path = (F4 / "synthetic" if synthetic else F4) / f"{name}.txt"
    return parse_submission(path.read_text(encoding="utf-8"))


def test_geron_cluster_purchases() -> None:
    """Three Geron insiders bought on 2025-02-27 (the S7 near miss: $206k in total)."""
    got = [(f.person, f.role, [(t.date, t.shares, t.price, t.value, t.planned) for t in f.purchases()])
           for f in map(load, ("0000950170-25-030327", "0000950170-25-030329", "0000950170-25-030330"))]  # fmt: skip
    day = date(2025, 2, 27)
    assert got == [
        ("Ziegler James", "EVP,  Chief Commercial Officer", [(day, D(100000), D("1.6"), D(160000), False)]),
        (
            "SCARLETT JOHN A",
            "director; Chairman, President and CEO",
            [(day, D(12500), D("1.765"), D("22062.5"), False)],
        ),
        ("Samuels Scott Alan", "EVP, Chief Legal Officer", [(day, D(15000), D("1.61"), D(24150), False)]),
    ]


def test_acceptance_time_is_eastern_converted_to_utc() -> None:
    """The SGML header's 06:01:05 (EST) is the submissions JSON's 11:01:05Z."""
    f = load("0000950170-25-030327")
    assert f.accession == "0000950170-25-030327"
    assert f.accepted_at == datetime(2025, 3, 3, 11, 1, 5, tzinfo=UTC)
    summer = header_acceptance("<ACCEPTANCE-DATETIME>20240618161229")
    assert summer == datetime(2024, 6, 18, 20, 12, 29, tzinfo=UTC)  # EDT is UTC-4
    assert header_acceptance("no header") is None


def test_checkbox_marks_every_transaction_planned_and_derivatives_are_excluded() -> None:
    amd = load("0000002488-24-000104")  # option exercise (M) + 10b5-1 sales, checkbox marked
    assert amd.checkbox_10b5_1 and all(t.planned for t in amd.transactions)
    assert any(t.derivative and t.code == "M" for t in amd.transactions)
    assert amd.purchases() == []


def test_footnote_alone_marks_planned() -> None:
    adi = load("0000006281-22-000181")  # 2022: before the checkbox existed; the plan is only in a footnote
    assert not adi.checkbox_10b5_1
    assert all(t.planned for t in adi.transactions)
    assert all("10b5-1" in adi.footnotes[i] for t in adi.transactions for i in t.footnote_ids)


def test_only_code_p_is_a_purchase() -> None:
    ttwo = load("0001127602-24-017715")  # D, S, J, G (gift in and out) and A: none is an open-market purchase
    assert {t.code for t in ttwo.transactions} == {"D", "S", "J", "G", "A"}
    assert ttwo.purchases() == []
    anet = load("0001596532-24-000253")
    assert anet.purchases() == [] and {t.code for t in anet.transactions} == {"S"}


def test_other_real_purchases() -> None:
    aort = load("0000784199-25-000043")
    assert [(t.shares, t.value) for t in aort.purchases()] == [(D(1500), D("37990.500")), (D(600), D("15150.00"))]
    vac = load("0001524358-25-000052")
    assert [(t.date, t.value) for t in vac.purchases()] == [(date(2025, 3, 4), D("116348.40"))]
    assert vac.role == "director"
    sei = load("0000950170-25-055869")  # an amendment (4/A) still reports its purchases
    assert sei.document_type == "4/A" and len(sei.purchases()) == 2 and sei.issuer_symbol == "SEI"


def test_synthetic_cluster() -> None:
    fs = [load(f"0009999901-25-{n:06d}", synthetic=True) for n in range(1, 7)]
    buys = [(f.person, t.value, t.planned) for f in fs for t in f.purchases()]
    assert buys == [
        ("DOE JANE", D("150000.00"), False),
        ("ROE RICHARD", D("124000.00"), False),
        ("POE ALEX", D("80000.00"), True),  # checkbox
        ("EXAMPLE CAPITAL FUND LP / EXAMPLE CAPITAL GP LLC", D("32200.00"), True),  # footnote only; joint = 1 person
        ("DOE JANE", D("16500.00"), False),
    ]
    assert any(t.derivative for t in fs[1].transactions)  # the CFO's option grant is parsed, never a purchase
    assert fs[3].role == "10% owner" and fs[5].purchases() == []
    assert fs[0].accepted_at == datetime(2025, 3, 10, 20, 5, tzinfo=UTC)


def test_dtd_and_entities_are_refused() -> None:
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><ownershipDocument>&a;</ownershipDocument>'
    with pytest.raises(Form4Error, match="DTD"):
        parse_xml(bomb)
    with pytest.raises(Form4Error, match="not an ownershipDocument"):
        parse_xml("<edgarSubmission/>")
    with pytest.raises(Form4Error, match="no <XML>"):
        parse_submission("<SEC-DOCUMENT>no xml here</SEC-DOCUMENT>")

"""Fact diffs and risk-factor diffs (Appendix F.6), entity matching (P-02) and risk tags (P-03)."""

from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path

from pipeline.facts import entities, risk_diff
from pipeline.facts.diff import Value, compute
from pipeline.facts.html_text import normalize_html

B = D(10) ** 9
SYN = Path(__file__).resolve().parents[2] / "fixtures" / "syn"


def v(num: str | None = None, low: str | None = None, high: str | None = None, unit: str = "usd") -> Value:
    def s(x: str | None) -> D | None:
        return None if x is None else D(x) * B

    return Value(s(num), s(low), s(high), unit)


def test_single_values() -> None:
    d = compute(v("38"), v("45"))
    assert (d.change_kind, d.delta_abs, d.delta_pct) == ("raised", D(7) * B, D("18.4"))
    assert d.computed_note == "$38.0B → $45.0B (+18.4%)"
    assert compute(v("45"), v("38")).change_kind == "lowered"
    assert compute(v("80"), v("80.3")).change_kind == "reaffirmed"  # +0.375% <= 0.5%
    assert compute(None, v("80")).change_kind == "new"


def test_ranges_midpoints_and_widths() -> None:
    assert compute(v(None, "70", "75"), v(None, "75", "80")).change_kind == "raised"
    assert compute(v(None, "70", "80"), v(None, "72", "78")).change_kind == "narrowed"
    assert compute(v(None, "72", "78"), v(None, "70", "80")).change_kind == "widened"
    assert compute(v(None, "70", "80"), v(None, "70.1", "80.1")).change_kind == "reaffirmed"


def test_units_and_withdrawals() -> None:
    assert compute(Value(D(500), None, None, "mw"), Value(D(2), None, None, "gw")).change_kind == "changed"
    w = compute(v("80"), v("80"), withdrawn=True)
    assert w.change_kind == "changed" and w.computed_note == "$80.0B → withdrawn"


def test_risk_factor_diff_on_f_syn() -> None:
    old, new = (normalize_html((SYN / f).read_text(encoding="utf-8"))
                for f in ("kyst_10k_2025_risk.htm", "kyst_10k_2026_risk.htm"))  # fmt: skip

    def section(n: object) -> list[risk_diff.Para]:
        s = next(x for x in n.section_map if x["name"] == "risk_factors")  # type: ignore[attr-defined]
        return risk_diff.paragraphs(n.text, int(s["char_start"]), int(s["char_end"]))  # type: ignore[attr-defined]

    changes = risk_diff.compare(section(old), section(new))
    kinds = sorted(c.kind for c in changes)
    assert kinds.count("added") == 1 and kinds.count("removed") == 1
    added = next(c for c in changes if c.kind == "added")
    text, s, e = risk_diff.quote(added)
    assert s is not None and e is not None and new.text[s:e] == text and len(text.split()) <= 25
    assert text.startswith("A significant share of our expected load growth comes from data center customers")
    removed = next(c for c in changes if c.kind == "removed")
    assert risk_diff.quote(removed)[0].startswith("Changes in federal and state tax law")


def test_risk_tags_keep_only_allowed_tags() -> None:
    got = risk_diff.parse_tags({"items": [{"id": "p1", "tags": ["data_center", "weather", "ai_demand"]},
                                          {"id": "zz", "tags": ["financing"]}]}, ["p1", "p2"])  # fmt: skip
    assert got == {"p1": ["ai_demand", "data_center"], "p2": []}


def test_entity_candidates_and_p02_parse() -> None:
    pool = [entities.Candidate("c:1", "NIMBUS COMPUTE CORP"), entities.Candidate("c:2", "Nimble Storage Inc"),
            entities.Candidate("e:3", "Keystone Power & Light Co.")]  # fmt: skip
    top = entities.candidates_for("Nimbus Compute", pool)
    assert top[0].id == "c:1"
    assert entities.normalize_name("Keystone Power & Light Co.") == "keystone power and light"
    got = entities.parse({"matches": [{"name": "Nimbus Compute", "candidate_id": "c:1", "kind": "company"},
                                      {"name": "Nimbus Compute", "candidate_id": "c:999", "kind": "company"},
                                      {"name": "Unknown Utility", "candidate_id": None, "kind": "utility"}]},
                         ["Nimbus Compute", "Unknown Utility"], {"c:1", "e:3"})  # fmt: skip
    assert got["Unknown Utility"].kind == "utility" and got["Unknown Utility"].candidate_id is None
    assert got["Nimbus Compute"].candidate_id is None  # the later answer names a candidate never offered

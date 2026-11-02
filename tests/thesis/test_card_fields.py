"""P-04's answer keeps only the card's fields (pipeline/thesis/validate.py card_fields: the fallback, research cards
and the samples; 2026-11-02: DeepSeek added a `card_type` key and the strict card schema failed every card)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.thesis import validate as v
from pipeline.thesis.validate import card_fields

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "card"


def test_an_extra_key_is_dropped_and_the_card_still_validates_strictly() -> None:
    good = json.loads((FIX / "good.json").read_text())
    pack = json.loads((FIX / "pack.json").read_text())
    noisy = {**good, "card_type": "thesis", "model_notes": "x"}
    assert not v.validate(noisy, pack, []).ok  # the schema stays strict
    clean = card_fields(noisy)
    assert clean == good and v.validate(clean, pack, []).ok


def test_unmarked_figures_in_inferences_and_assumptions_are_marked_assumed() -> None:
    """docs/SPEC_ISSUES.md 70: a figure the model left unmarked gets "(assumed)"; a marked one is left alone; facts and
    why_mispriced are untouched (those figures must match the pack)."""
    from pipeline.thesis.validate import ASSUMED, card_fields, mark_assumed, sentence_numbers

    text = (
        "Inference: margins reach 0.2755, and the $600 million order converts over the years at 12% (assumed) a year."
    )
    out = mark_assumed(text)
    assert out == ("Inference: margins reach 0.2755 (assumed), and the $600 million (assumed) order converts over the "
                   "years at 12% (assumed) a year.")  # fmt: skip
    assert all(ASSUMED.match(out[p.end :]) for p in sentence_numbers(out))
    assert mark_assumed(out) == out  # idempotent
    doc = {
        "inferences": [text],
        "assumptions": ["Assumption: 3 plants by 2028."],
        "why_mispriced": [{"text": "Up 5%."}],
    }
    got = card_fields(doc, {"week_end": "2026-10-30"})
    assert got["inferences"] == [out]
    assert got["assumptions"] == ["Assumption: 3 (assumed) plants by 2028."]  # 2028 reads as a year, not a figure
    assert got["why_mispriced"] == [{"text": "Up 5%."}]


def test_a_stated_scales_bounds_are_not_figures() -> None:
    """docs/SPEC_ISSUES.md 70: "62.5 on a 0-100 scale" holds one figure (62.5); a bare "0" or "100" still counts."""
    from pipeline.thesis.validate import sentence_numbers

    def written(t: str) -> list[str]:
        return [t[p.start : p.end] for p in sentence_numbers(t)]

    assert written("The evidence score is 62.5 on a 0-100 scale and the gap is 58.3.") == ["62.5", "58.3"]
    assert written("Scored 40 on a 0 to 100 range.") == ["40"]
    assert "100" in written("Margins rose from 0 to 100 basis points.")

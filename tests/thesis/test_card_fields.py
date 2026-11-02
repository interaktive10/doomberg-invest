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

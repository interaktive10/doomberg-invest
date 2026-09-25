"""M4 review R2-F1: India's share counts are paid-up capital / face value and are never adjusted, so a 1:1 bonus
issue (x2) or a face-value split (10 -> 2, x5) must not read as dilution in R4 or S5; real dilution still does."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import yaml

from pipeline.settings import REPO_ROOT
from pipeline.signals import redflags, s05_capital_discipline
from pipeline.signals.base import Ctx
from pipeline.signals.series import Quarter, Series

CFG = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
FLAGS = yaml.safe_load((REPO_ROOT / "config" / "redflags.yaml").read_text(encoding="utf-8"))
WEEK = date(2026, 9, 18)


def ends(n: int) -> list[date]:
    out, y, m = [], 2026, 6
    for _ in range(n):
        out.append(date(y, m, 30 if m in (6, 9) else 31))
        y, m = (y, m - 3) if m > 3 else (y - 1, m + 9)
    return list(reversed(out))


def series(counts: list[int]) -> Series:
    return Series([Quarter(e, {"shares_outstanding": D(c), "revenue": D(100)}) for e, c in
                   zip(ends(len(counts)), counts, strict=True)], "in")  # fmt: skip


def r4(counts: list[int]) -> redflags.FlagResult:
    return redflags.r4(Ctx("c", "in", WEEK, series(counts), CFG), FLAGS["R4"])


def test_r4_bonus_issue_is_not_dilution() -> None:
    f = r4([100] * 6 + [200] * 3)  # a 1:1 bonus in the December 2025 quarter (inside the YoY window)
    assert f.status == "clear" and f.inputs["share_change_yoy"] == 0.0 and f.inputs["splits"] == ["2025-12-31 x2"]


def test_r4_face_value_split_is_not_dilution() -> None:
    f = r4([100] * 6 + [500] * 3)  # face value 10 -> 2
    assert f.status == "clear" and f.inputs["splits"] == ["2025-12-31 x5"]


def test_r4_real_dilution_still_fires_next_to_the_bonus_rule() -> None:
    assert r4([100] * 6 + [115] * 3).status == "fired"  # +15%: no split ratio within 3%
    both = r4([100] * 5 + [200] * 2 + [230] * 2)  # a bonus, then a 15% issue: still dilution
    assert both.status == "fired" and both.inputs["share_change_yoy"] == 0.15


def test_s5_path_b_ignores_yearly_bonus_issues() -> None:
    """Two yearly 1:1 bonuses and then none looked like +100% dilution twice and a stop: S5 path B (0.6)."""
    s = series([100] * 5 + [200] * 4 + [400] * 4)
    r = s05_capital_discipline.compute(Ctx("c", "in", WEEK, s, CFG))
    assert not r.fired and r.inputs["share_change_prior_years"] == [0.0, 0.0]

"""M4-05: Evidence / Gap / bucket math (BRIEF §1.7, §4.8), including the 2-family cap, soft-flag penalties and the
12-week novelty rule of the weekly shortlist."""

from __future__ import annotations

import uuid
from decimal import Decimal as D

import pytest
import yaml

from pipeline.settings import REPO_ROOT
from pipeline.signals.base import SignalResult
from pipeline.signals.buckets import Ranked, bucket, market_cap_ok, shortlist
from pipeline.signals.scores import Weights, evidence, gap

CFG = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))["scores"]
W = Weights.load()
UNIVERSE = {
    m: yaml.safe_load((REPO_ROOT / "config" / f"universe_{m}.yaml").read_text(encoding="utf-8")) for m in ("us", "in")
}


def fired(**strengths: str) -> dict[str, SignalResult]:
    return {k: SignalResult(True, D(v), {}) for k, v in strengths.items()}


def test_weights_start_equal() -> None:
    assert W.version == "w0-equal" and set(W.signals.values()) == {D(1)} and set(W.families.values()) == {D(1)}


def test_family_takes_its_top_two_and_caps_at_one() -> None:
    ev = evidence(fired(S1="1", S3="0.5", S4="0.3", S7="0.6"), 0, W, CFG)
    assert ev.contributions["fundamentals"] == D(1) and ev.contributions["behavior"] == D("0.6")
    assert ev.raw == D("1.6") and ev.score == D(80) and ev.families == ("fundamentals", "behavior")
    ev2 = evidence(fired(S3="0.3", S4="0.2", S5="0.2"), 0, W, CFG)  # top 2 of 3: 0.3 + 0.2
    assert ev2.contributions["fundamentals"] == D("0.5")


def test_s11_and_the_capex_family_left_in_weights_yaml_count_for_nothing() -> None:
    """Overhaul PR 4 (docs/SPEC_ISSUES.md 52): S11 and the capex family went with the Capex Desk, but
    config/weights.yaml (protected) keeps their weights until a weights PR drops them. Evidence reads only
    config/signals.yaml's families, so they load without error and change no score, even with a stray S11 result."""
    assert "S11" in W.signals and "capex" in W.families  # still in weights.yaml
    assert "capex" not in CFG["families"] and all("S11" not in ids for ids in CFG["families"].values())
    heavy = Weights(W.version, {**W.families, "capex": D(5)}, {**W.signals, "S11": D(5)}, W.context)
    with_s11 = evidence(fired(S1="0.8", S7="0.6", S11="1"), 0, heavy, CFG)
    assert with_s11 == evidence(fired(S1="0.8", S7="0.6"), 0, W, CFG)
    assert "capex" not in with_s11.contributions and with_s11.families == ("fundamentals", "behavior")


def test_unfired_signals_do_not_count() -> None:
    res = {**fired(S1="0.8"), "S2": SignalResult(False, D(0), {})}
    assert evidence(res, 0, W, CFG).contributions["fundamentals"] == D("0.8")


def test_one_family_is_capped_at_55() -> None:
    heavy = Weights(W.version, {**W.families, "fundamentals": D("2.4")}, W.signals, W.context)
    one = evidence(fired(S1="1", S2="1"), 0, heavy, CFG)
    assert one.raw == D("2.4") and one.score == D(55) and one.capped
    two = evidence(fired(S1="1", S2="1", S7="0.2"), 0, heavy, CFG)
    assert two.score == D(100) and not two.capped


def test_soft_flags_subtract_ten_each_floored_at_zero() -> None:
    base = evidence(fired(S1="1", S7="0.6"), 0, W, CFG).score
    assert evidence(fired(S1="1", S7="0.6"), 2, W, CFG).score == base - 20
    assert evidence(fired(S1="0.1"), 3, W, CFG).score == 0


def test_gap_is_the_mean_of_available_context_scores() -> None:
    assert gap({"C1": D(60), "C2": D(40), "C3": None}, W, 2) == D(50)
    assert gap({"C1": D(60), "C2": None, "C3": None}, W, 2) is None


@pytest.mark.parametrize(
    ("ev", "gp", "fams", "hard", "mcap", "expected"),
    [
        ("60", "50", 2, False, True, "candidate"),
        ("59.99", "80", 2, False, True, "early"),
        ("59.99", "80", 1, False, True, "none"),  # early needs 2 families
        ("40", "50", 2, False, True, "early"),
        ("39.99", "90", 3, False, True, "none"),
        ("70", "49.99", 3, False, True, "priced_in"),
        ("90", "90", 3, True, True, "excluded"),  # any hard red flag
        ("90", None, 3, False, True, "none"),  # Gap needs >= 2 context metrics
        ("90", "90", 3, False, False, "none"),  # below the market-cap floor
    ],
)
def test_buckets(ev: str, gp: str | None, fams: int, hard: bool, mcap: bool, expected: str) -> None:
    assert bucket(D(ev), None if gp is None else D(gp), fams, hard, CFG["buckets"], mcap) == expected


def test_market_cap_floor_per_market() -> None:
    assert market_cap_ok("us", D(300_000_000), UNIVERSE) and not market_cap_ok("us", D(299_999_999), UNIVERSE)
    assert market_cap_ok("in", D(5_000_000_000), UNIVERSE) and not market_cap_ok("in", None, UNIVERSE)


def test_shortlist_takes_ten_new_candidates_by_evidence_then_gap() -> None:
    ids = [uuid.UUID(int=i) for i in range(14)]
    rows = [Ranked(ids[i], D(90 - i), D(60), "candidate") for i in range(12)]
    rows += [Ranked(ids[12], D(95), D(90), "early"), Ranked(ids[13], D(80), D(70), "candidate")]
    seen = {ids[0], ids[1]}  # shortlisted in the last 12 weeks
    got = shortlist(rows, seen, int(CFG["weekly_new_candidates"]))
    assert len(got) == 10 and ids[0] not in {r.company_id for r in got} and ids[12] not in {r.company_id for r in got}
    assert [r.company_id for r in got[:3]] == [ids[2], ids[3], ids[4]]
    assert (got[8].company_id, got[9].company_id) == (ids[13], ids[10])  # Evidence 80 each: the higher Gap first

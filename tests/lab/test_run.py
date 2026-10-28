"""M8-05: a real Lab run waits for the Twelve Data download (lab-prices.yml, no human step) and says why; the weights
PR's body carries each signal's verdict."""

from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path

import pytest
import yaml

from pipeline.lab import run
from pipeline.lab.evaluate import Stat
from pipeline.lab.prices import DownloadState, TickerState
from pipeline.lab.proposals import NOT_TESTABLE, REOPEN, pr_body, propose, verdict

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = yaml.safe_load((ROOT / "config" / "weights.yaml").read_text(encoding="utf-8"))


def test_a_run_without_prices_is_blocked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--market", "us", "--prices", str(tmp_path / "p.csv.gz"), "--state", str(tmp_path / "s.json")]
    assert run.main(args) == run.BLOCKED_EXIT
    out = capsys.readouterr().out
    assert (
        "lab: BLOCKED: no Lab prices yet: lab-prices.yml downloads them from Twelve Data into the database "
        "(lab_us_month_prices) with no human step"
    ) in out and "BLOCKED(human" not in out


def test_a_download_in_progress_or_blocked_blocks_the_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    prices, state = tmp_path / "p.csv", tmp_path / "s.json"
    prices.write_text("ticker,month_end,close\nA,2024-01-31,1\n", encoding="utf-8")
    DownloadState("1day", "partial", None, {"A": TickerState("ok"), "B": TickerState("pending", 1)}).save(state)
    args = ["--market", "us", "--prices", str(prices), "--state", str(state)]
    assert run.main(args) == run.BLOCKED_EXIT
    assert "the Twelve Data download has 1 of 2 tickers" in capsys.readouterr().out
    DownloadState(None, "blocked", "AAPL's daily series starts 2015-01-02 ...").save(state)
    assert run.main(args) == run.BLOCKED_EXIT
    assert "lab: BLOCKED: the Twelve Data download is blocked: AAPL's daily series" in capsys.readouterr().out
    DownloadState(None, "pending").save(state)
    assert run.main(args) == run.BLOCKED_EXIT
    assert "hasn't started" in capsys.readouterr().out
    cfg = run.lab_config()
    complete = DownloadState("1day", "complete", None, {"A": TickerState("ok")})
    assert run.blocked_reason(prices, complete, cfg) is None and run.blocked_reason(prices, None, cfg) is None
    assert run.blocked_reason(tmp_path / "missing.csv.gz", complete, cfg) is not None


def test_india_waits_for_eight_quarters(capsys: pytest.CaptureFixture[str]) -> None:
    assert run.main(["--market", "in"]) == 0
    assert "not enabled" in capsys.readouterr().out


def test_the_database_is_where_lab_prices_keeps_them() -> None:
    """BRIEF §11.5, docs/SPEC_ISSUES.md 55: lab-prices.yml keeps the prices and the download's state in the database
    (pipeline_state, under config/lab.yaml's names) and lab.yml reads them from there; nothing goes into a release of
    the public repository (the old lab-data-v1 release is only read once, to move its files, then deleted)."""
    p = run.lab_config()["prices"]
    assert "pipeline_state" in (ROOT / "docs" / "BRIEF.md").read_text(encoding="utf-8")
    wf = ROOT / ".github" / "workflows"
    lab, prices = ((wf / n).read_text(encoding="utf-8") for n in ("lab.yml", "lab-prices.yml"))
    for k in ("asset", "state"):
        pair = f"{p['stored_as'][k]}=.cache/lab/{p[k]}"
        assert pair in lab and lab.count("python -m pipeline.db.state get") == 1
        assert prices.count(pair) == 2  # read before the download, stored after it
    assert "gh release upload" not in lab + prices and "gh release create" not in lab + prices
    assert "d_us_txt" not in lab + prices and "Stooq" not in lab + prices


def s(sid: str, period: str, mean: float, t: float) -> Stat:
    return Stat(sid, 12, period, 50, mean, mean, None, None, t, None)


def test_one_verdict_per_signal_from_the_weight_rule() -> None:
    """§4.10.5: works where the rule promotes, hurts where it demotes, unproven otherwise; S7-S12 aren't testable
    yet and keep their weights whatever their statistics, so S9 never earns weight."""
    rules = WEIGHTS["lab_rules"]
    assert verdict(s("S1", "out_of_sample", 0.05, 2.0), s("S1", "in_sample", 0.01, 1), rules) == "works"
    assert verdict(s("S1", "out_of_sample", 0.05, 2.0), s("S1", "in_sample", -0.01, 1), rules) == "unproven"
    assert verdict(s("S1", "out_of_sample", -0.05, -2.0), None, rules) == "hurts"
    assert verdict(None, None, rules) == "unproven"
    stats = [s("S3", "out_of_sample", 0.06, 3.1), s("S3", "in_sample", 0.02, 1.0), s("S5", "out_of_sample", -0.06, -3),
             s("S9", "out_of_sample", 0.09, 5.0), s("S9", "in_sample", 0.02, 4.0), s("S7", "out_of_sample", -0.1, -4),
             s("L2", "out_of_sample", 0.04, 2.4), s("L2", "in_sample", 0.01, 0.3)]  # fmt: skip
    not_testable = run.lab_config()["not_testable"]
    assert not_testable == [f"S{i}" for i in range(7, 13)]
    props = {p.signal_id: p for p in propose(stats, WEIGHTS, 12, not_testable)}
    assert (props["S3"].verdict, props["S3"].new) == ("works", D("1.5"))
    assert (props["S5"].verdict, props["S5"].new) == ("hurts", D("0.0"))
    assert (props["S1"].verdict, props["S1"].new) == ("unproven", D("1.0"))
    assert (props["L2"].verdict, props["L2"].new) == ("works", D("1.5"))
    assert (props["L1"].verdict, props["L1"].new) == ("unproven", D("0.0"))
    for sid in not_testable:
        assert props[sid].verdict == NOT_TESTABLE and props[sid].new == props[sid].old, sid


def test_the_weights_pr_body_carries_the_verdicts_and_how_to_run_the_checks() -> None:
    stats = [s("S3", "out_of_sample", 0.06, 3.1), s("S3", "in_sample", 0.02, 1.0)]
    props = propose(stats, WEIGHTS, 12, run.lab_config()["not_testable"])
    body = pr_body(props, WEIGHTS["lab_rules"], 12)
    assert "| signals.S3 | works | 1.0 | 1.5 |" in body and "| signals.S1 | unproven | 1.0 | 1.0 |" in body
    assert "| signals.S9 | not testable yet | 1.0 | 1.0 |" in body and "S9 never earns weight" in body
    assert "| legacy.L1 | unproven | 0.0 | 0.0 |" in body and "human-approved label" in body
    assert REOPEN == "close and reopen to run the checks, then add human-approved" and REOPEN in body
    lab = (ROOT / ".github" / "workflows" / "lab.yml").read_text(encoding="utf-8")
    assert '--pr-body "$RUNNER_TEMP/weights_pr.md"' in lab and '--body-file "$RUNNER_TEMP/weights_pr.md"' in lab

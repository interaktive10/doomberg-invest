"""The text reader's scope on stage names (docs/SPEC_ISSUES.md 50, 58; analysis audit P2), the parts without a
database: when a stage name is read (again), which of its filings it reads against a thesis's, whose SEC submissions
are read, the work order, and that P-03 is gone. tests/db/test_facts_pipeline.py runs the same rules through the
database."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import yaml

from pipeline.db import facts_repo
from pipeline.db.models import Company
from pipeline.facts import run
from pipeline.facts.fetch import FILING_DAYS, STAGE_DAYS, FilingRef, scope_filings
from pipeline.llm.prompt import PROMPT_DIR, PROMPTS
from pipeline.llm.quotas import Quotas
from pipeline.settings import REPO_ROOT
from pipeline.us.submissions import Submissions, parse_submissions

DAY = date(2026, 9, 25)


def at(days_ago: int, hour: int = 0) -> datetime:
    return datetime(DAY.year, DAY.month, DAY.day, hour, tzinfo=UTC) - timedelta(days=days_ago)


def test_a_stage_name_is_read_while_queued_and_again_after_100_days() -> None:
    assert run.READ_AGAIN_DAYS == 100 and run.STAGE_MIN_EVIDENCE == 40
    assert run.due(None, queued=False, day=DAY)  # never read
    assert not run.due(at(99), queued=False, day=DAY)  # read 99 days ago: not yet
    assert not run.due(at(100), queued=False, day=DAY)  # 100 days to the day: not yet
    assert run.due(at(100) - timedelta(seconds=1), queued=False, day=DAY)  # more than 100 days: its next report
    assert run.due(at(3), queued=True, day=DAY)  # read 3 days ago, but filings of its are still queued


def submissions(rows: list[tuple[int, str, str]]) -> Submissions:
    """(days before DAY, form, items) -> SEC submissions with those filings, accepted at 21:00 UTC."""
    recent: dict[str, list[str]] = {k: [] for k in ("accessionNumber", "form", "filingDate", "reportDate",
                                                    "acceptanceDateTime", "items", "primaryDocument")}  # fmt: skip
    for k, (ago, form, items) in enumerate(rows):
        filed = DAY - timedelta(days=ago)
        recent["accessionNumber"].append(f"0000999001-26-{k:06d}")
        recent["form"].append(form)
        recent["filingDate"].append(filed.isoformat())
        recent["reportDate"].append("")
        recent["acceptanceDateTime"].append(f"{filed.isoformat()}T21:00:00.000Z")
        recent["items"].append(items)
        recent["primaryDocument"].append(f"doc{k}.htm")
    return parse_submissions({"cik": "999001", "name": "Nimbus Compute Corp.", "fiscalYearEnd": "0630",
                              "tickers": ["NMBS"], "filings": {"recent": recent, "files": []}})  # fmt: skip


HISTORY = [
    (500, "10-K", ""),  # older than a thesis's 400 days
    (300, "10-K", ""),
    (150, "10-Q", ""),
    (130, "8-K", "8.01"),  # a press release older than a stage name's 120 days
    (60, "8-K", "7.01"),
    (20, "10-Q", ""),  # the latest report
    (15, "10-Q/A", ""),  # amendments aren't read
    (10, "8-K", "1.01,9.01"),  # an agreement: theses only
    (5, "8-K", "2.02,9.01"),  # results
    (3, "8-K", "5.02"),  # no text item
]


def forms(refs: list[FilingRef]) -> list[tuple[int, str, tuple[str, ...]]]:
    return sorted(((DAY - r.accepted_at.date()).days, r.form, r.items) for r in refs)


def test_stage_names_read_the_latest_report_and_releases_of_120_days_theses_400() -> None:
    assert (STAGE_DAYS, FILING_DAYS) == (120, 400)
    subs = submissions(HISTORY)
    assert forms(scope_filings(subs, DAY, thesis=False)) == [
        (5, "8-K", ("2.02", "9.01")),
        (20, "10-Q", ()),
        (60, "8-K", ("7.01",)),
    ]
    assert forms(scope_filings(subs, DAY, thesis=True)) == [
        (5, "8-K", ("2.02", "9.01")),
        (10, "8-K", ("1.01", "9.01")),
        (20, "10-Q", ()),
        (60, "8-K", ("7.01",)),
        (130, "8-K", ("8.01",)),
        (150, "10-Q", ()),
        (300, "10-K", ()),
    ]
    # a stage name whose latest report is older than 120 days reads only its releases
    late = submissions([(150, "10-Q", ""), (40, "8-K", "2.02")])
    assert forms(scope_filings(late, DAY, thesis=False)) == [(40, "8-K", ("2.02",))]


def test_submissions_are_read_only_for_new_or_indexed_names() -> None:
    t, s = run.RANK["thesis"], run.RANK["stage"]
    scope = {"A": s, "B": s, "C": s, "D": t, "E": t}
    checked = {"A": s, "C": s, "D": s, "E": t, "Z": s}  # Z left the scope
    got = run.to_fetch(scope, checked, indexed={"C", "Q"})
    # B is new, C filed (the daily EDGAR index lists it), D became a thesis (its 400 days); A and E are known
    assert got == {"B": s, "C": s, "D": t}
    assert run.to_fetch(scope, None, set()) == scope  # no record of the last run: every name is read


def job(rank: int, days_ago: int, name: str) -> run.Job:
    c = Company(id=uuid4(), market="us", name=name)
    return rank, at(days_ago), run.DocJob(c, "10-Q", f"https://www.sec.gov/{name}", "", at(days_ago)), None


def test_theses_come_before_stage_names_each_newest_first() -> None:
    t, s = run.ORDER.index("thesis"), run.ORDER.index("stage")
    jobs = [job(s, 1, "stage-new"), job(t, 90, "thesis-old"), job(s, 30, "stage-old"), job(t, 2, "thesis-new")]
    assert [j[2].company.name for j in run.work_order(jobs)] == ["thesis-new", "thesis-old", "stage-new", "stage-old"]
    # config/quotas.yaml work_order names the same places in the same order (PR 3 review TXT-4)
    assert Quotas.load().work_order == run.ORDER == ("thesis", "board", "one_fact", "stage", "excluded")
    assert run.ORDER.index("thesis") == run.RANK["thesis"] == 0  # a thesis is first in both


def stage(bucket: str, gap: str | None) -> facts_repo.StageName:
    return facts_repo.StageName(uuid4(), None, False, bucket, None if gap is None else Decimal(gap))


def test_the_stage_reads_the_boards_then_one_fact_from_a_candidate_then_the_rest_excluded_last() -> None:
    """docs/SPEC_ISSUES.md 58: a board's names first, then those one verified S9 fact (0.4, 20 Evidence points) would
    make a Candidate: Evidence >= 40 (the stage) with Gap >= the Candidate's 50. Priced-in and unpriced names wait;
    Excluded names come last, since a hard flag stays whatever the text says."""
    place = {name: k for k, name in enumerate(run.ORDER)}
    assert [run.stage_order(stage(b, "40")) for b in ("candidate", "watch", "early")] == [place["board"]] * 3
    assert run.stage_order(stage("none", "50")) == run.stage_order(stage("none", "88.5")) == place["one_fact"]
    assert run.stage_order(stage("none", "49.9")) == run.stage_order(stage("none", None)) == place["stage"]
    assert run.stage_order(stage("priced_in", "20")) == place["stage"]
    assert run.stage_order(stage("excluded", "95")) == place["excluded"]
    buckets = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))["scores"]["buckets"]
    assert run.ONE_FACT_MIN_GAP == Decimal(str(buckets["candidate"]["min_gap"]))
    assert run.BOARDS == {"candidate", "watch", "early"} <= set(buckets)


def test_a_stage_name_moving_up_the_order_keeps_its_filing_window() -> None:
    """Submissions are read again only when a stage name becomes a thesis (its 400 days), not when it moves between
    the stage's places: queue_us compares RANK (a thesis's window or a stage name's), not the place in ORDER."""
    s = run.RANK["stage"]
    checked = {"A": s, "B": s}
    coarse = {cik: min(r, s) for cik, r in {"A": run.ORDER.index("board"), "B": run.ORDER.index("excluded")}.items()}
    assert run.to_fetch(coarse, checked, indexed=set()) == {}


def test_p03_is_no_longer_called() -> None:
    """A 10-Q or 10-K makes no P-03 call: the prompt, its files, the risk diff and its run stage are gone, and the
    record-cassettes samples have no P-03 (F-SYN keeps its two risk-factor versions)."""
    from pipeline.facts.evaluate import SYN, load_truth
    from pipeline.facts.samples import inputs

    assert "P-03" not in PROMPTS and not list(PROMPT_DIR.glob("P-03.*"))
    assert importlib.util.find_spec("pipeline.facts.risk_diff") is None
    assert not hasattr(run, "risk_changes") and "risk_changes" not in run.TextStats.__dataclass_fields__
    truth = load_truth()
    assert set(inputs(SYN, truth)) == {"P-02", "P-07"}
    assert {"kyst_10k_2025_risk.htm", "kyst_10k_2026_risk.htm"} <= {d["file"] for d in truth["documents"]}


def test_the_stats_record_is_json() -> None:
    """TextStats goes to the runs row as JSON; `checked` (CIK -> rank) is the next run's record."""
    stats = run.TextStats("2026-09-25", checked={"0000999001": run.RANK["stage"]})
    assert json.loads(json.dumps(asdict(stats)))["checked"] == {"0000999001": 1}

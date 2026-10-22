"""The digest body (overhaul PR 5; pipeline/digest/weekly.py build): "## This week" (the funnel), "## To do",
"## What changed", then "## Health" with one line naming the late sources and the Actions minutes line; no LLM table,
no source table, no Capex or Lab section; a week without scores still goes out and says why. The database reads are
replaced by fakes here; tests/db/test_thesis.py builds it from real rows (and the M6-06 snapshot)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from pipeline.db.models import Company, SourceHealth
from pipeline.digest import changes, weekly
from pipeline.digest.changes import Name, WeekRow

W = date(2026, 9, 18)
NOW = datetime(2026, 9, 19, 3, tzinfo=UTC)
APP = "https://doomberg.example"
ECHO = uuid.UUID("00000000-0000-4000-8000-0000000000e1")
MTDR = uuid.UUID("00000000-0000-4000-8000-0000000000e2")
MINUTES = "Actions: 812 of 2,000 this cycle, projected 1,340."
FUNNEL = {"market": "us", "scored": 4659, "stage": 456, "candidates": 4, "shortlisted": 1, "one_family": 440}


def fake(monkeypatch: pytest.MonkeyPatch, *, funnel: list[dict[str, Any]], names: list[Name],
         cards: list[dict[str, Any]], reviewing: list[dict[str, Any]], health: list[SourceHealth]) -> None:  # fmt: skip
    companies = [Company(id=ECHO, market="us", name="Echo Grid Corp.", ticker="ECHO"),
                 Company(id=MTDR, market="us", name="Matador Resources", ticker="MTDR")]  # fmt: skip
    monkeypatch.setattr(weekly.repo, "companies", lambda conn: companies)
    monkeypatch.setattr(weekly.repo, "source_health", lambda conn: health)
    monkeypatch.setattr(weekly.thesis_repo, "funnel", lambda conn, week, ev, fam: funnel)
    monkeypatch.setattr(weekly.thesis_repo, "cards_to_decide", lambda conn: cards)
    monkeypatch.setattr(weekly.thesis_repo, "in_review", lambda conn, week: reviewing)
    monkeypatch.setattr(weekly.changes, "gather", lambda conn, week, companies: (names, []))


def sections(body: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", body, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def row(ev: str, bucket: str, fired: str) -> WeekRow:
    return WeekRow(Decimal(ev), Decimal(60), bucket, ("fundamentals", "text"), frozenset(fired.split()))


def test_the_body_has_the_funnel_to_do_what_changed_and_health(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, funnel=[FUNNEL],
         names=[Name(ECHO, "ECHO", row("72.5", "candidate", "S1 S9"), None, 1),
                Name(MTDR, "MTDR", row("48", "none", "S9"), row("62", "candidate", "S4 S9"))],
         cards=[{"name": "Echo Grid Corp.", "market": "us", "ticker": "ECHO", "nse_symbol": None}],
         reviewing=[{"name": "Kappa Cables", "market": "in", "ticker": None, "nse_symbol": "KAPPA"}],
         health=[SourceHealth(source="sec", last_success=NOW),
                 SourceHealth(source="twelvedata", last_success=datetime(2026, 9, 7, 6, tzinfo=UTC)),
                 SourceHealth(source="stooq", last_error="stale: gone", stale=True)])  # fmt: skip
    title, body = weekly.build(None, W, APP, now=NOW, actions=[MINUTES])  # type: ignore[arg-type]
    assert title == "Doomberg weekly — 2026-W38"
    assert body.startswith("Week ending 2026-09-18. Research only: no orders, no price alerts.\n\n## This week\n")
    s = sections(body)
    assert list(s) == ["This week", "To do", "What changed", "Health"]
    assert s["This week"] == ("US 4,659 → stage 456 → candidates 4 → new 1 · 440 of 456 fire one family, "
                              "capped at 55")  # fmt: skip
    assert s["To do"] == ("- Cards to accept or dismiss: 1 (Echo Grid Corp. (ECHO))\n"
                          "- Theses in review: 1 (Kappa Cables (KAPPA))")  # fmt: skip
    assert s["What changed"] == (
        f"- [ECHO]({APP}/company/{ECHO}) new candidate (#1): S1, S9 fired (fundamentals, text), Evidence 72.5, Gap 60\n"
        f"- [MTDR]({APP}/company/{MTDR}) left Candidate: S4 stopped, Evidence 62 → 48")  # fmt: skip
    assert s["Health"] == ("**Stale data:** twelvedata (no success for 11 days; SLA 8). Signals and scores that read "
                           f"these sources may be out of date.\n\n{MINUTES}")  # fmt: skip
    assert "stooq" not in body  # a dead source (no SLA) is never named
    for word in ("LLM", "Provider", "| Source |", "Capex", "Lab", "gainer", "loser", "return"):
        assert word not in body, word


def test_a_week_without_scores_still_goes_out_and_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, funnel=[], names=[], cards=[], reviewing=[],
         health=[SourceHealth(source="sec", last_success=datetime(2026, 9, 1, 6, tzinfo=UTC))])  # fmt: skip
    why = weekly.unscored_why({"US_RESULT": "failure", "US_RAN": "true", "SCORES_RESULT": "skipped"})
    _, body = weekly.build(None, W, APP, now=NOW, why_unscored=why)  # type: ignore[arg-type]
    s = sections(body)
    assert s["This week"] == ("**Candidates are missing this week:** no scores were written for 2026-09-18 (the US "
                              "data run failed, so nothing was scored; see health below).")  # fmt: skip
    assert s["To do"] == "Nothing needs you this week."
    assert s["What changed"] == changes.UNSCORED
    assert s["Health"] == ("**Stale data:** sec (no success for 17 days; SLA 8). Signals and scores that read these "
                           "sources may be out of date.")  # fmt: skip


def test_a_quiet_week_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, funnel=[{**FUNNEL, "candidates": 0, "shortlisted": 0}], names=[], cards=[], reviewing=[],
         health=[SourceHealth(source="sec", last_success=NOW)])  # fmt: skip
    _, body = weekly.build(None, W, APP, now=NOW, actions=[MINUTES])  # type: ignore[arg-type]
    s = sections(body)
    assert s["What changed"] == changes.NOTHING == "Nothing changed this week."
    assert s["Health"] == f"Sources: none late or stale.\n\n{MINUTES}"
    _, none = weekly.build(None, W, APP, now=NOW)  # type: ignore[arg-type]
    assert sections(none)["Health"] == "Sources: none late or stale." and "Actions:" not in none

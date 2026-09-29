"""R4's India acquisition exception (M4 review R1-F5): takeover-code disclosures and new subsidiaries don't exempt a
share-count jump; a real acquisition does, also after the announcement itself is pruned (kind 'acquisition')."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal as D
from uuid import uuid4

import yaml

from pipeline.india import daily
from pipeline.india.announcements import Announcement, is_acquisition
from pipeline.settings import REPO_ROOT
from pipeline.signals import redflags
from pipeline.signals.base import Ctx, Event
from pipeline.signals.series import Quarter, Series

SIGNALS = yaml.safe_load((REPO_ROOT / "config" / "signals.yaml").read_text(encoding="utf-8"))
FLAGS = yaml.safe_load((REPO_ROOT / "config" / "redflags.yaml").read_text(encoding="utf-8"))
WEEK = date(2026, 9, 18)
ENDS = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31),
        date(2026, 6, 30)]  # fmt: skip
SAST = Event(
    "announcement",
    date(2026, 8, 1),
    {
        "category": "Disclosure under SEBI Takeover Regulations",
        "text": "Regulation 29(2) of SEBI (Substantial Acquisition of Shares and Takeovers) Regulations, 2011",
    },
)
SUBSIDIARY = Event(
    "announcement",
    date(2026, 8, 1),
    {"category": "Acquisition", "text": "Incorporation of a wholly owned subsidiary for the solar business"},
)


def r4(*events: Event) -> redflags.FlagResult:
    quarters = [Quarter(e, {"shares_outstanding": D(100) if i < 2 else D(115)}) for i, e in enumerate(ENDS)]
    ctx = Ctx("c", "in", WEEK, Series(quarters, "in"), SIGNALS, events=list(events))
    return next(f for f in redflags.compute_all(ctx, FLAGS) if f.flag_id == "R4")


def test_r4_india_takeover_code_disclosure_is_not_an_acquisition() -> None:
    assert r4().status == "fired"  # +15% shares, no acquisition
    assert r4(SAST).status == "fired" and r4(SUBSIDIARY).status == "fired"


def test_r4_india_acquisition_eight_months_back_still_exempts() -> None:
    deal = Event("acquisition", date(2026, 1, 20), {"category": "Acquisition",
                 "text": "Acquisition of 100% equity of Grid Cables Pvt Ltd"})  # fmt: skip
    got = r4(deal)
    assert got.status == "clear" and got.inputs["acquisitions"] == ["acquisition:2026-01-20"]


def test_r4_india_ingestion_keeps_acquisitions_beyond_the_announcement_prune() -> None:
    def ann(category: str, text: str) -> Announcement:
        return Announcement(
            "ARVL",
            "INE0",
            "Aravalli",
            category,
            text,
            date(2026, 1, 20),
            datetime(2026, 1, 20, 9, tzinfo=UTC),
            "https://nsearchives.nseindia.com/a.pdf",
            "1",
            False,
        )

    assert is_acquisition("Acquisition", "Acquisition of 100% equity of Grid Cables Pvt Ltd")
    assert not is_acquisition(SAST.detail["category"], SAST.detail["text"])
    assert not is_acquisition("Acquisition", SUBSIDIARY.detail["text"])
    events = daily._events([ann("Acquisition", "Acquisition of Grid Cables Pvt Ltd"),
                            ann(SAST.detail["category"], SAST.detail["text"])], {"ARVL": uuid4()})  # fmt: skip
    assert sorted(e.kind for e in events) == ["acquisition", "announcement", "announcement"]

"""What changed this week (overhaul PR 5; pipeline/digest/changes.py): one line per company with its biggest change,
the shortlist first, at most 20 lines, an Evidence move counted at exactly 10, exits worded without price moves,
reaffirmed diffs left out, and nothing private read. tests/db/test_thesis.py runs it against the database (with
private fields seeded with sentinels) and in the digest body."""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pipeline.db import facts_repo, repo, thesis_repo
from pipeline.digest import changes, weekly
from pipeline.digest.changes import FactNews, Name, WeekRow, change, lines

APP = "https://doomberg.example"
T = datetime(2026, 9, 17, 12, tzinfo=UTC)


def cid(n: int) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-4000-8000-{n:012d}")


def row(evidence: str, bucket: str = "candidate", gap: str | None = "61", fired: str = "S1 S9",
        families: tuple[str, ...] = ("fundamentals", "text"), hard: str = "", soft: str = "") -> WeekRow:  # fmt: skip
    return WeekRow(Decimal(evidence), None if gap is None else Decimal(gap), bucket, families,
                   frozenset(fired.split()), frozenset(hard.split()), frozenset(soft.split()))  # fmt: skip


def name(n: int, code: str, now: WeekRow | None, before: WeekRow | None, rank: int | None = None) -> Name:
    return Name(cid(n), code, now, before, rank)


def text(n: Name) -> str:
    c = change(n)
    assert c is not None
    return c.text


def test_a_line_names_the_biggest_change_and_its_reason() -> None:
    mtdr = name(1, "MTDR", row("48", "none", fired="S9", families=("text",)), row("62", fired="S4 S9"))
    assert text(mtdr) == "left Candidate: S4 stopped, Evidence 62 → 48"
    priced = name(2, "PRCD", row("66", "priced_in", gap="48"), row("66", gap="55"))
    assert text(priced) == "now priced in (Gap 48)"
    early = name(3, "ERLY", row("64", fired="S1 S7 S9"), row("55", "early", fired="S1 S9"))
    assert text(early) == "moved from Early to Candidate: S7 fired, Evidence 55 → 64"
    entered = name(4, "NEWB", row("52", "early", fired="S2 S7"), row("38", "none", fired="S2"))
    assert text(entered) == "entered Early: S7 fired, Evidence 38 → 52"
    excluded = name(5, "EXCL", row("50", "excluded", hard="R3"), row("50", "early"))
    assert text(excluded) == "left Early: R3 hard flag"
    gone = name(6, "GONE", None, row("61"))
    assert text(gone) == "left Candidate: not scored this week"
    out = lines([mtdr], [], APP)
    assert out == [f"- [MTDR]({APP}/company/{cid(1)}) left Candidate: S4 stopped, Evidence 62 → 48"]


def test_watch_moves_are_bucket_changes() -> None:
    """SPEC_ISSUES 56: Watch is a bucket like the others: entering it, leaving it, and moving on to Early or the board
    each make a line; a Watch name that changed nothing makes none."""
    one = ("fundamentals",)
    joined = name(1, "WTCH", row("50", "watch", gap="72", fired="S4", families=one),
                  row("40", "none", gap="72", fired="S4", families=one, soft="R2"))  # fmt: skip
    assert text(joined) == "entered Watch: R2 cleared, Evidence 40 → 50"
    left = name(2, "LEFT", row("50", "none", gap="58", fired="S4", families=one), row("50", "watch", gap="64",
                fired="S4", families=one))  # fmt: skip
    assert text(left) == "left Watch: Gap 58"
    up = name(3, "UPGR", row("72", fired="S4 S7", families=("fundamentals", "behavior")),
              row("50", "watch", fired="S4", families=one))  # fmt: skip
    assert text(up) == "moved from Watch to Candidate: S7 fired, Evidence 50 → 72"
    still = row("50", "watch", fired="S4", families=one)
    assert change(name(4, "SAME", still, still)) is None


def test_one_line_per_company_with_its_biggest_change() -> None:
    """A bucket change beats an Evidence move, which beats a signal or flag that started or stopped; a company gets one
    line, with every reason in it."""
    both = name(1, "BOTH", row("40", "none", fired="S9", soft="R1"), row("62", fired="S4 S9"))
    out = lines([both], [], APP)
    assert len(out) == 1 and out[0].endswith("left Candidate: S4 stopped, R1 soft flag, Evidence 62 → 40")
    names = [
        name(1, "SIGN", row("61", fired="S1 S7 S9"), row("60")),  # a signal started, Evidence +1
        name(2, "MOVE", row("75"), row("63")),  # Evidence +12, same bucket
        name(3, "BCKT", row("58", "early"), row("61")),  # Candidate -> Early
        name(4, "SAME", row("61"), row("61")),  # nothing changed: no line
    ]
    codes = [line.split("]")[0].removeprefix("- [") for line in lines(names, [], APP)]
    assert codes == ["BCKT", "MOVE", "SIGN"]


def test_the_shortlist_comes_first_in_rank_order() -> None:
    names = [
        name(1, "BIGM", row("80"), row("40", "none")),
        name(2, "SEC2", row("70"), None, rank=2),
        name(3, "TOP1", row("72.5", gap="61.2"), row("50", "none"), rank=1),
    ]
    out = lines(names, [], APP)
    assert [x.split("]")[0] for x in out] == ["- [TOP1", "- [SEC2", "- [BIGM"]
    assert out[0] == (f"- [TOP1]({APP}/company/{cid(3)}) new candidate (#1): S1, S9 fired (fundamentals, text), "
                      "Evidence 72.5, Gap 61.2")  # fmt: skip


def test_at_most_20_lines() -> None:
    names = [name(i, f"C{i:02d}", row("75"), row("60")) for i in range(30)]
    facts = [FactNews(cid(i), f"C{i:02d}", "backlog", "backlog", "raised", "$1.0B → $1.2B (+20.0%)", T)
             for i in range(5)]  # fmt: skip
    out = lines(names, facts, APP)
    assert len(out) == changes.MAX_LINES == 20 and all("Evidence 60 → 75" in x for x in out)


def test_an_evidence_move_counts_at_exactly_10() -> None:
    assert text(name(1, "TEN", row("70"), row("60"))) == "Evidence 60 → 70"
    assert text(name(2, "DOWN", row("50.5", "candidate"), row("60.5"))) == "Evidence 60.5 → 50.5"
    assert change(name(3, "NINE", row("69.9"), row("60"))) is None  # 9.9: not a change on its own
    assert text(name(4, "NINE", row("69.9", fired="S1 S7 S9"), row("60"))) == "S7 fired, Evidence 60 → 69.9"


def test_exits_are_worded_without_price_moves() -> None:
    exits = [
        name(1, "PRCD", row("66", "priced_in", gap="31"), row("66", gap="70")),
        name(2, "GAPL", row("52", "none", gap="45"), row("52", "early", gap="55")),
        name(3, "NOGP", row("61", "none", gap=None), row("61", gap="58")),
        name(4, "EXIT", row("44", "none", fired="S1"), row("61")),
    ]
    out = lines(exits, [], APP)
    assert [x.split(") ", 1)[1] for x in out] == [  # bucket changes, the bigger Evidence move first
        "left Candidate: S9 stopped, Evidence 61 → 44", "left Early: Gap 45", "left Candidate: Gap not known this week",
        "now priced in (Gap 31)"]  # fmt: skip
    for line in out:
        low = line.lower()
        assert "%" not in line and not any(w in low for w in ("return", "gain", "rall", "ran ", "price rose",
                                                               "price fell", "up ", "down "))  # fmt: skip


def test_new_facts_and_diffs_follow_with_reaffirmed_ones_left_out() -> None:
    late = datetime(2026, 9, 18, 9, tzinfo=UTC)
    facts = [
        FactNews(cid(1), "ECHO", "backlog", "total backlog", "raised", "$38.0B → $45.0B (+18.4%)", T),
        FactNews(cid(1), "ECHO", "capex_guidance", "2026 capex", "reaffirmed", "$2.0B → $2.0B (+0.0%)", late),
        FactNews(cid(2), "KAPA", "order_win", "a $600 million order from a hyperscale customer", "new",
                 "new: $600.0M", late),
    ]  # fmt: skip
    names = [name(3, "MOVE", row("75"), row("63"))]
    out = lines(names, facts, APP)
    assert out == [
        f"- [MOVE]({APP}/company/{cid(3)}) Evidence 63 → 75",
        f"- [KAPA]({APP}/company/{cid(2)}) new verified order win: a $600 million order from a hyperscale customer "
        "($600.0M)",
        f"- [ECHO]({APP}/company/{cid(1)}) backlog raised: $38.0B → $45.0B (+18.4%)",
    ]  # fmt: skip
    assert not any("reaffirmed" in x or "capex" in x for x in out)


def test_nothing_to_say_is_an_empty_list() -> None:
    assert lines([name(1, "SAME", row("61"), row("61")), name(2, "NONE", None, None)], [], APP) == []
    assert change(name(3, "FRST", row("45", "none"), None)) is None  # first scored outside a bucket: nothing to compare


def test_week_rows_read_fired_signals_and_fired_flags() -> None:
    w = datetime(2026, 9, 18).date()
    rows = changes.week_rows(
        [{"company_id": cid(1), "week_end": w, "evidence": Decimal("62.5"), "gap": None, "families": ["text"],
          "bucket": "none"}],
        [{"company_id": cid(1), "week_end": w, "signal_id": "S9"}],
        [{"company_id": cid(1), "week_end": w, "flag_id": "R3", "hard": True},
         {"company_id": cid(1), "week_end": w, "flag_id": "R1", "hard": False}],
    )  # fmt: skip
    assert rows == {(cid(1), w): WeekRow(Decimal("62.5"), None, "none", ("text",), frozenset({"S9"}),
                                         frozenset({"R3"}), frozenset({"R1"}))}  # fmt: skip


def test_nothing_private_is_read() -> None:
    """What changed, To do and the funnel read only the weekly outputs, the facts and company names: no journal,
    position size, review note, dismissal or override reason, post-mortem or candidate action (the digest is a GitHub
    issue). tests/db/test_thesis.py seeds those fields with sentinels and checks the body."""
    readers = [changes.gather, changes.week_rows, thesis_repo.previous_scored_week, thesis_repo.funnel,
               thesis_repo.bucket_company_ids, thesis_repo.scores_of, thesis_repo.fired_signals_of,
               thesis_repo.fired_flags_of, thesis_repo.cards_to_decide, thesis_repo.in_review,
               thesis_repo.shortlist, thesis_repo.scored, facts_repo.week_facts, repo.research_company_ids,
               weekly.build, weekly.to_do]  # fmt: skip
    for f in readers:
        src = inspect.getsource(f).lower()
        for word in ("journal", "portfolio_pct", "postmortem", "reviews", "candidate_actions", "dismissed_reason",
                     "override_reason", "reason", "llm"):  # fmt: skip
            assert word not in src, (f.__qualname__, word)

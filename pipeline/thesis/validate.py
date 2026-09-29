"""Thesis-card validation (BRIEF §4.9): a card is rejected if any rule fails.

1. The pack is a valid EvidencePack (extra or mistyped fields fail; M6 review R1-F4), and the card follows the P-04
   schema (field types and counts; summary <= 60 words).
2. Every sentence in `facts` and `why_mispriced` cites >= 1 pack id: inline ([m:...], [f:...], [s:...], [c:...]) or,
   for a one-sentence item, in its `cites`; every cited id (there and in `risks`) exists in the pack. Sentences
   cover the whole text: any line break, or ., !, ? or \u2026 followed by a space, an opening bracket or quote, or a
   capital, ends one. It runs on inside a number ($1.87), after Mr./No./vs., after an initial of a name (John A.
   Smith), and after an abbreviation (Corp., Inc., Jr., St., U.S., N.V.) unless a word that opens sentences follows
   ("Microsoft Corp. The customer" is two sentences; "U.S. GAAP" and "Corp. (NMBS) received" are one; M6 review
   R1-F2, R2-F1, R3-F2).
3. Every number in those sentences (digits, a leading point, or number words with a unit: "fifty percent") equals,
   with its sign, a value under a cited id, or a delta computed by code between two cited periods of the same metric
   (later minus earlier, change, ratio), within the rounding of the digits written. A percent (or percentage points)
   compares with a value x 100, and with the raw value only when the item's unit is percent; an amount written with
   a currency compares only with cited money in that currency ("Rs 1.25 billion" is not $1.25 billion and "$212
   million" is not a share count; M6 review R3-F3). The words give a figure its sign: next to it ("down 21.6%", "a
   21.6% decline", "a loss of $50 million", "a drop in revenue of 21.6%") or, for a change that isn't a level, the
   nearest movement word in its clause ("declined year over year by 21.6%", "fell sharply, by 21.6%"). A move
   between two cited periods of one metric runs from the earlier period to the later one, with words that match
   it: "to X from Y", "from Y to X", "X, down from Y", "X versus Y" and "fell to X" (M6 review R1-F3, R2-F2, R3-F1);
   "doubled", "halved", "tenfold", "up by a third" need a cited ratio that says so. Dates (2026-06-30, June 30,
   2026, June 30), fiscal labels (FY2026, Q2, Q2'26), period names ("the three months ended", "trailing 12-month"),
   scales ("out of 100", "/100"), form names (10-Q, Item 2.01) and signal names (S1, C2) are labels, not numbers, and
   a label never takes the figure after it ("Q2 45%", "Q2 1200 servers"); a four-digit number alone is a year only
   in a year's context ("in 2026", "Q2 2026"; not "2000 customers" or "2000 AI servers"; M6 review R2-F3, R2-F4,
   R3-F4, R3-F5). Only [m:...]-style citations are removed, any other bracketed text is checked.
4. `inferences` start with "Inference:" and `assumptions` with "Assumption:"; a number there is followed by
   "(assumed)".
5. Kill criteria: a kill-criteria metric id of the pack with a value, an operator, a threshold (null only for
   `changes`) the pack value doesn't already meet, and a check_after date after the next filing window.
6. No hype word (config/terms.yaml `hype`) anywhere in the card, after folding case, apostrophes, hyphens and spacing
   ("can’t lose", "multi-bagger", "sure-shot", "to the  moon"; M6 review R1-F11).
7. P-05 (claim support) for every fact and why-mispriced item that passes the checks above, when a router is given:
   the sentence, the quotes of the facts it cites, and the cited items with their labels and the moves between cited
   periods, because a figure that equals some cited value can still name the wrong item, period or size (M6 review
   R3-F1). Unsupported -> rejected; no provider -> a note (thesis-ingest.yml, which has the keys, checks again).

`python -m pipeline.thesis.validate --week 2026-W38` checks data/thesis_cards/<week>/*.json against the packs in
data/thesis_queue/<week>.json (exit 1 when a card fails).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from pipeline.facts import numbers
from pipeline.llm.router import Deferred, Router
from pipeline.settings import REPO_ROOT
from pipeline.thesis.evidence_pack import ClaimInput, EvidencePack, is_kill_metric, units_by_id, values_by_id

CITE = re.compile(r"\[((?:m|f|s|c):[^\]\s]+)\]")
CITATION = re.compile(r"\[(?:m|f|s|c):[^\]\s]+\]")
MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
LABELS = re.compile(
    r"\[(?:m|f|s|c):[^\]\s]+\]"  # citations only: any other bracketed text is checked (M6 review R1-F3)
    r"|\b\d{4}-\d{2}-\d{2}\b"  # dates
    rf"|\b{MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b"  # June 30, 2026 (M6 review R1-F8)
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH},?\s+\d{{4}}\b"  # 30 June 2026
    rf"|\b{MONTH}\s+\d{{4}}\b"  # June 2026
    # June 30 / 30 June without a year (M6 review R2-F4), but not "May 5%"
    rf"|\b{MONTH}\s+(?:[12]\d|3[01]|0?[1-9])(?:st|nd|rd|th)?\b(?!\s*(?:%|per\s?cent|[.,]\d|million|billion|crore|lakh))"
    rf"|\b(?:[12]\d|3[01]|0?[1-9])(?:st|nd|rd|th)?\s+{MONTH}(?![\w.])"
    # period names (M6 review R2-F4): "the three months ended", "12 months to", "the trailing twelve months"
    r"|\b(?:three|six|nine|twelve|thirteen|twenty[- ]six|thirty[- ]nine|fifty[- ]two|3|6|9|12|13|26|39|52)[- ]"
    r"(?:months?|weeks?)\s+(?:ended|ending|to|through|thru|until)\b"
    # "the trailing twelve months", "trailing 12-month revenue", "a 12-month period" (M6 review R3-F5)
    r"|\b(?:trailing|last|past|latest|next)[\s-]+(?:twelve|12|four|4)[\s-]+(?:months?|quarters?)\b"
    r"|\b(?:three|six|nine|twelve|3|6|9|12)-month\b"
    # scales: "62.5 out of 100", "62.5/100" (M6 review R3-F5)
    r"|\bout\s+of\s+(?:100|10|5)\b(?![.,]?\d)"
    r"|(?<=\d)\s?/\s?(?:100|10|5)\b(?![.,]?\d)"
    # fiscal labels (M6 review R2-F3: a label never takes the figure after it, "Q2 45%")
    r"|\b(?:Q[1-4]|H[12]|[1-4]Q|[12]H)\s?(?:FY|CY)\s?'?\d{2,4}\b"  # Q2FY26, Q2 FY2026
    r"|\b(?:FY|CY)\s?'?\d{2,4}(?:\s?[-\u2013/]\s?'?\d{2,4})?\b"  # FY2026, FY 2026, FY26, FY2025-26
    # Q2, Q2'26, 2Q26; a four-digit number after a space is read on its own: "Q2 2026" is a year, "Q2 1200 servers"
    # a figure (M6 review R3-F4)
    r"|\b(?:Q[1-4]|H[12])(?:\s?'\d{2}\b|\d{4}\b)?(?!\d)"
    r"|\b(?:[1-4]Q|[12]H)(?:\s?'?\d{2}\b|\d{4}\b)?(?!\d)"
    r"|\b(?:10-K|10-Q|8-K|20-F|40-F|6-K|S-1|13F|13D|13G|DEF\s?14A|Form\s\d+[A-Z]?)\b"  # form names
    r"|\bItem\s\d+(?:\.\d+)?[A-Z]?\b"  # 8-K / 10-K items
    r"|(?-i:\b[SRCL]\d{1,2}\b)",  # signal, flag, context and Lab names (S1, R4, C2, L3), capitals only (R2-F3)
    re.I,
)
END = re.compile(r"[.!?\u2026]+[\"'\u201d\u2019)\]]*")
# After these a period never ends a sentence ("Mr. Smith", "No. 5", "vs. Intel", "e.g. Nvidia").
RUN_ON = frozenset("mr mrs ms dr no nos vs fig approx est dept e.g i.e".split())
# After these (and dotted initials: N.V., S.A., E.U.) a period ends a sentence only before a word in OPENING:
# "Nimbus Compute Corp. received", "U.S. GAAP", "Corp. (NMBS) received" and "Corp. Chief Executive Jane Doe said"
# run on; "is Microsoft Corp. The customer", "John Smith Jr. The customer" and "Wall St. A hyperscale provider" are
# two sentences (M6 review R2-F1, R3-F2).
ABBREVIATIONS = frozenset(
    "inc corp co ltd llc plc lp etc jr sr st bros u.s u.k u.n jan feb mar apr jun jul aug sep sept oct nov dec a.m "
    "p.m".split()
)
OPENING = frozenset(
    "a an the this that these those it its we our they their there he she his her in on at for as by but and or so "
    "yet however also after before since while when if although though management revenue sales backlog orders "
    "remaining operating net free capital".split()
)
LINE_BREAK = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
OPENERS = "([{\"'\u201c\u2018"
METRIC_ID = re.compile(r"^m:(?P<metric>[a-z0-9_]+):(?P<end>\d{4}-\d{2}-\d{2})$")
FALL_WORDS = (
    r"down|fell|falls?|fallen|falling|declined?|declines|declining|decreased?|decreases|decreasing|dropped|drops?|"
    r"dropping|lower|shrank|shrinks?|shrunk|shrinking|contracted|contracting|slipped|slipping|slid|slides?|sliding|"
    r"lost|plunged|plummeted|slumped|sank|sunk|tumbled|dipped|eased|retreated|weakened|collapsed|deteriorated|cut|"
    r"reduced|lowered|shed"
)
# Movement verbs (and up/down) that give a change or a move its direction from further back in the clause; not nouns
# ("growth slowed to 27.6%"), comparatives ("lower costs lifted income to") or verbs that take another object ("cut
# prices, lifting revenue to"; M6 review R3-F1).
MOVE_DOWN = (
    r"down|fell|falls?|fallen|falling|declined?|declines|declining|decreased?|decreases|decreasing|dropped|drops?|"
    r"dropping|slipped|slipping|slid|slides?|sliding|shrank|shrinks?|shrunk|shrinking|contracted|contracting|plunged|"
    r"plummeted|slumped|sank|sunk|tumbled|dipped|eased|retreated|weakened|collapsed|deteriorated|slowed|decelerated|"
    r"halved"
)
MOVE_UP = (
    r"up|rose|rises?|risen|rising|grew|grows?|grown|growing|increased?|increases|increasing|climbed|climbs?|climbing|"
    r"jumped|jumps?|jumping|gained|gains?|gaining|expanded|expands?|expanding|surged|surges?|surging|soared|soars?|"
    r"soaring|advanced|improved|improves?|improving|accelerated|rebounded|recovered|doubled|tripled"
)
DROP_NOUNS = r"drops?|declines?|decreases?|falls?|reductions?|contractions?|slides?|slumps?|dips?|loss|losses|cuts?"
APPROX = (r"(?:about\s+|approximately\s+|roughly\s+|nearly\s+|almost\s+|some\s+|around\s+|over\s+|more\s+than\s+|"
          r"less\s+than\s+)?")  # fmt: skip
CUR = r"(?:US\$|\$|\u20b9|Rs\.?\s?|INR\s?|USD\s?|\u20ac|\u00a3)?"
DET = r"(?:the\s+|a\s+|an\s+|its\s+|their\s+)?"
DOWN = re.compile(
    rf"\b(?:{FALL_WORDS}|loss\s+of|losses\s+of|deficit\s+of|outflows?\s+of|decline\s+of|decrease\s+of|"
    r"drop\s+of|fall\s+of|reduction\s+of|cut\s+of|negative)\s+(?:by\s+)?(?:about\s+|approximately\s+|"
    r"roughly\s+|nearly\s+|almost\s+|some\s+|over\s+|more\s+than\s+)?[$\u20b9]?$",
    re.I,
)
FOLLOW_DOWN = re.compile(
    r"^\s*(?:below|lower\s+than|less\s+than|under)\s+(?:a\s+year\s+(?:earlier|ago|before)|last\s+year|the\s+(?:prior|"
    r"previous|year[- ]earlier))"
    # "a 27.6% decline", "44.8% lower", "a $50 million loss" (M6 review R2-F2)
    r"|^\s*(?:(?:year[- ]over[- ]year|y/y|yoy)\s+)?(?:declines?|decreases?|drops?|falls?|reductions?|contractions?|"
    r"slumps?|plunges?|dips?|loss(?:es)?|lower|less|down|shortfalls?|deficits?)\b",
    re.I,
)
# "a drop in revenue of 27.6%", "a decline of 27.6%" (M6 review R3-F1)
DOWN_OF = re.compile(rf"\b(?:{DROP_NOUNS})\s+(?:in\s+[^\d.;:]{{1,40}}?\s+)?of\s+{APPROX}{CUR}$", re.I)
FOLLOW_UP = re.compile(r"^\s*(?:(?:year[- ]over[- ]year|y/y|yoy)\s+)?(?:increases?|rises?|gains?|growth|jumps?|higher|"
                       r"more|up|above|improvements?|expansion)\b", re.I)  # fmt: skip
# A level, not a change: "to $1.25 billion", "from $980 million", "was 16.5%", "a margin of 16.5%"
ENDPOINT = re.compile(rf"\b(?:to|from|at|of|versus|vs\.?|compared\s+(?:with|to)|against|was|were|is|are|be|been|"
                      rf"reached|reaching|totaled|totalled|totaling|totalling|hit|stood\s+at|came\s+in\s+at)\s+"
                      rf"{DET}{APPROX}{CUR}$", re.I)  # fmt: skip
BY = re.compile(rf"\bby\s+{APPROX}{CUR}$", re.I)
MINUS = re.compile(r"(?<![\w.])[-\u2212]\s?[$\u20b9]?$")
# The nearest movement word in a figure's clause gives a change its direction (M6 review R3-F1).
GOVERN = re.compile(rf"\b(?:(?P<down>{MOVE_DOWN})|(?P<up>{MOVE_UP}))\b", re.I)
CLAUSE_BREAK = re.compile(r"[;:]|\b(?:while|whereas|but|although|though|despite)\b", re.I)
# "X, down from Y" / "X, up from Y": X is the later level, Y the earlier one (M6 review R3-F1)
FILL = r"[^.;:\d]{0,40}?"
UP_DOWN_FROM = re.compile(
    rf"^{FILL}[\s,(\u2013\u2014-]+(?:or\s+)?(?:(?P<up>up|higher|more|an?\s+(?:increase|rise|gain|jump)|rising|"
    rf"climbing|growing|increasing)|(?P<down>down|lower|less|an?\s+(?:decrease|decline|drop|fall)|falling|declining|"
    rf"decreasing|dropping|sliding))\s+from\s+{DET}{APPROX}{CUR}$",
    re.I,
)
# "X versus Y": X is the later level unless the words say it is the earlier one ("X a year earlier versus Y")
VERSUS = re.compile(rf"^(?P<fill>{FILL})[\s,(]+(?:versus|vs\.?|compared\s+(?:with|to)|against)\s+{DET}{APPROX}"
                    rf"{CUR}$", re.I)  # fmt: skip
EARLIER = re.compile(r"\b(?:a\s+year\s+(?:earlier|ago|before)|last\s+year|(?:prior|previous|year[- ]earlier|"
                     r"year[- ]ago)\s+(?:year|quarter|period)|previously|earlier)\b", re.I)  # fmt: skip
# A multiplier claims a ratio of two cited periods: "doubled" 2, "halved" 0.5, "up by half" 1.5 (M6 review R2-F2).
MULTIPLIER = re.compile(
    r"\b(?P<q>more\s+than\s+|nearly\s+|almost\s+)?(?P<w>doubl(?:ed|ing|es)|tripl(?:ed|ing|es)|quadrupl(?:ed|ing|es)|"
    r"halv(?:ed|ing|es)|(?:two|three|four|five|six|seven|eight|nine|ten|\d{1,2})[- ]?fold|"
    r"(?:up|rose|grew|increased|gained|jumped|climbed|expanded)\s+(?:by\s+)?(?:a\s+)?half|"
    r"(?:down|fell|declined|dropped|cut|shrank|slid)\s+(?:by\s+)?(?:a\s+)?half|cut\s+in\s+half|"
    # "grew by a third", "fell by one-quarter" (M6 review R3-F1)
    r"(?:up|rose|grew|increased|gained|jumped|climbed|expanded|down|fell|declined|dropped|cut|shrank|slid)\s+by\s+"
    r"(?:a\s+|one[- ])(?:third|quarter|fifth))\b(?![- ]?part|\s+of\b)",
    re.I,
)
FOLD = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
FRACTION = {"half": 1 / 2, "third": 1 / 3, "quarter": 1 / 4, "fifth": 1 / 5}
TO_FROM = re.compile(r"\bto\s+(?:about\s+|approximately\s+|roughly\s+)?(?:US\$|\$|\u20b9|Rs\.?\s?|INR\s?)?$", re.I)
FROM_ = re.compile(r"^[^.;\d]{0,60}?\bfrom\s+(?:about\s+|approximately\s+|roughly\s+)?(?:US\$|\$|\u20b9|Rs\.?\s?|"
                   r"INR\s?)?$", re.I)  # fmt: skip
FROM_TO = re.compile(r"\bfrom\s+(?:about\s+|approximately\s+|roughly\s+)?(?:US\$|\$|\u20b9|Rs\.?\s?|INR\s?)?$", re.I)
TO_ = re.compile(r"^[^.;\d]{0,60}?\bto\s+(?:about\s+|approximately\s+|roughly\s+)?(?:US\$|\$|\u20b9|Rs\.?\s?|"
                 r"INR\s?)?$", re.I)  # fmt: skip
# A bare four-digit number is a year only in a year's context (M6 review R2-F3): "in 2026", "2026 revenue", "since
# 2019", "by 2030,"; "has 2000 customers" and "its 1995 orders" are figures.
YEAR_BEFORE = frozenset("in since by until till through thru during before after fiscal calendar year from between "
                        "versus vs early late mid".split())  # fmt: skip
YEAR_AFTER = frozenset("fiscal financial calendar year years quarter quarters guidance results plan plans budget capex "
                       "outlook target targets report annual revenue revenues sales earnings and or to through versus "
                       "vs was were is will when as compared levels level peak low high first second third fourth full "
                       "half season period gaap ebitda ebit eps".split())  # fmt: skip
ASSUMED = re.compile(r"^[^.;,]{0,25}?\(assumed\)", re.I)
OPERATORS = ("<", "<=", ">", ">=", "==", "changes")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cited(Strict):
    text: str = Field(min_length=1)
    cites: list[str]


class Kill(Strict):
    metric_id: str
    operator: Literal["<", "<=", ">", ">=", "==", "changes"]
    threshold: Decimal | None
    check_after: date
    why: str = Field(min_length=1)


class Read(Strict):
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)


class Card(Strict):
    summary: str
    facts: list[Cited] = Field(min_length=3, max_length=8)
    why_mispriced: list[Cited] = Field(min_length=1, max_length=4)
    inferences: list[str] = Field(min_length=1, max_length=5)
    assumptions: list[str] = Field(min_length=2, max_length=5)
    risks: list[Cited] = Field(min_length=2, max_length=5)
    kill_criteria: list[Kill] = Field(min_length=2, max_length=4)
    read_next: list[Read] = Field(min_length=1, max_length=3)

    @field_validator("summary")
    @classmethod
    def _sixty_words(cls, v: str) -> str:
        if len(v.split()) > 60:
            raise ValueError("summary is longer than 60 words")
        return v


@dataclass
class Result:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def hype_words(root: Path = REPO_ROOT) -> list[str]:
    doc = yaml.safe_load((root / "config" / "terms.yaml").read_text(encoding="utf-8"))
    return [str(w) for w in doc.get("hype") or []]


# ---------------------------------------------------------------- numbers

GLUED_CURRENCY = re.compile(r"(?<![A-Za-z])(?:Rs\.?|INR|USD|EUR|GBP)(?=\d)", re.I)
LEADING_POINT = re.compile(r"(?<![\w.,])\.(?=\d)")  # ".95", "$.5 billion" (M6 review R3-F4)
POINTS = re.compile(r"^\s?(?:percentage[- ]points?|pp\b|ppts?\b)", re.I)  # a percent (M6 review R3-F5)
# Currencies the number parser reads as dollars or not at all (M6 review R3-F3)
FOREIGN_BEFORE = re.compile(r"(?:(?<![A-Za-z])(?!US)[A-Z]{1,2}\$|¥|\bJPY|\bCNY|\bRMB|\bCHF)\s?$")
FOREIGN_AFTER = re.compile(r"^\s?(?:euros?|pounds?(?:\s+sterling)?|sterling|yen|yuan|renminbi|(?:swiss\s+)?francs?)\b",
                           re.I)  # fmt: skip
QUARTER_BEFORE = re.compile(r"\b(?:Q[1-4]|H[12]|[1-4]Q|[12]H)\s$")
# A pack item's money: metric units that are currency codes, and facts in these units (their `currency` says which)
NOT_MONEY = frozenset({"shares", "count", "ratio", "percent", "score"})
MONEY_FACT_UNITS = frozenset({"usd", "usd_per_year"})
SECTIONS = ("metrics", "signals", "context", "facts", "ownership", "insiders", "kill_metrics")
NOT_FOR_P05 = frozenset({"id", "quote", "url", "source", "document_kind", "published_at", "subject_key"})


def _unglue(m: re.Match[str]) -> str:
    """ "Rs.50" -> "Rs 50" (still rupees); "Rs50" -> "R 50", "INR50" -> "IN 50": the same length, so offsets hold, and
    the figure is parsed and checked (M6 review R2-F3)."""
    w = m.group(0)
    return w[:-1] + " "


def _clean(text: str) -> str:
    return GLUED_CURRENCY.sub(_unglue, LABELS.sub(lambda m: " " * len(m.group(0)), text))


def _parse(clean: str) -> list[numbers.Parsed]:
    """numbers.parse, plus a figure written with a leading point (".95", "$.5 billion"; M6 review R3-F4); "percentage
    points" read as a percent (R3-F5); an amount in a currency the parser reads as dollars or not at all ("C$",
    "euros", "yen") marked foreign (R3-F3)."""
    found = numbers.parse(clean)
    for m in LEADING_POINT.finditer(clean):
        padded = numbers.parse(f"{clean[: m.start()]}0{clean[m.start() :]}")
        p = next((q for q in padded if q.start == m.start()), None)
        if p is not None:
            found.append(replace(p, start=m.start(), end=p.end - 1, range_with=None))
    out = []
    for p in sorted(found, key=lambda q: q.start):
        after = clean[p.end :]
        points = POINTS.match(after) if p.unit is None and p.currency is None else None
        if points:
            p = replace(p, unit="percent", end=p.end + points.end())
        if FOREIGN_BEFORE.search(clean[: p.start]) or (p.currency is None and FOREIGN_AFTER.match(after)):
            p = replace(p, currency="foreign")
        out.append(p)
    return out


def _is_year(clean: str, p: numbers.Parsed, years: tuple[int, int], after_label: bool = False) -> bool:
    """A bare four-digit number within `years` is a year when a year word follows it ("2026 revenue", "2026 and") or
    nothing word-like does ("by 2030,"), or a year word comes before it ("in", "since", "fiscal"). After a quarter
    label it is the label's year unless a lower-case word follows ("Q2 2026", "Q2 2026 Nimbus", but "Q2 2000
    servers"); elsewhere a capital after it doesn't make it a year ("2000 AI servers"; M6 review R2-F3, R3-F4)."""
    if not years[0] <= p.numeral <= years[1]:
        return False
    after = re.match(r"\s*([A-Za-z]+)", clean[p.end :])
    if after is None or after.group(1).lower() in YEAR_AFTER:
        return True
    if after_label:
        return not after.group(1)[0].islower()
    before = re.search(r"([A-Za-z]+)\W*$", clean[: p.start])
    return before is not None and before.group(1).lower() in YEAR_BEFORE


def _figures(text: str, years: tuple[int, int]) -> tuple[str, list[numbers.Parsed]]:
    """The figures in a sentence, and the sentence with labels and the other numbers (years, number words without a
    unit) blanked at the same offsets. A figure is a number written with digits, or a number word with a unit,
    currency or scale ("fifty percent"; "one of the two largest" is not); a four-digit number alone is a year only in
    a year's context (not "2,000", "2000th", "2000 MW" or "2000 customers")."""
    clean = _clean(text)
    chars = list(clean)
    out = []
    for p in _parse(clean):
        written = clean[p.start : p.end]
        if not any(ch.isdigit() for ch in written):
            figure = p.unit is not None or p.currency is not None or p.scale_word is not None
        else:
            four = re.fullmatch(r"\d{4}", written) is not None
            ordinal = re.match(r"(?:st|nd|rd|th)\b", clean[p.end : p.end + 3], re.I) is not None
            label = QUARTER_BEFORE.search(text[: p.start]) is not None
            figure = not (four and not ordinal and _is_year(clean, p, years, label))
        if figure:
            out.append(p)
        else:
            chars[p.start : p.end] = " " * (p.end - p.start)
    return "".join(chars), out


def sentence_numbers(text: str, years: tuple[int, int] = (1900, 2100)) -> list[numbers.Parsed]:
    """The figures in a sentence, labels left out (see _figures)."""
    return _figures(text, years)[1]


def _governing(before: str) -> int:
    """The direction of the nearest movement word before a figure within its clause (not across ;, :, "while",
    "but", "although", "despite"): -1 a fall ("declined year over year by", "fell sharply, by", "a drop in revenue
    of"), +1 a rise, 0 none (M6 review R3-F1)."""
    words = list(GOVERN.finditer(CLAUSE_BREAK.split(before)[-1]))
    if not words:
        return 0
    return -1 if words[-1].group("down") else 1


def sign(text: str, p: numbers.Parsed) -> int:
    """-1 when the words say the figure is a fall or a loss, else +1. Words next to it decide first ("down 21.6%", "a
    loss of $50 million", "a drop in revenue of 21.6%", "3% below a year earlier", "-3.3%", "a 27.6% increase"); a
    level stays positive ("to $1.25 billion", "from", "at", "was 16.5%", "a margin of 16.5%"); a change (a percent,
    or an amount after "by") takes the direction of the nearest movement word in its clause ("declined year over
    year by 27.6%", "fell sharply, by 27.6%"; M6 review R3-F1)."""
    before, after = text[: p.start], text[p.end :]
    if DOWN.search(before) or DOWN_OF.search(before) or FOLLOW_DOWN.match(after) or MINUS.search(before):
        return -1
    if FOLLOW_UP.match(after) or ENDPOINT.search(before):
        return 1
    if p.unit == "percent" or BY.search(before):
        return _governing(before) or 1
    return 1


@dataclass(frozen=True)
class Candidates:
    """What a cited figure may equal: the cited values (with whether the item's unit is percent), and the deltas
    between two cited periods of one metric, later against earlier (difference, change, ratio); an amount written
    with a currency only the cited money in that currency (`money`; M6 review R3-F3)."""

    raw: tuple[tuple[Decimal, bool], ...]
    differences: tuple[tuple[Decimal, str], ...]  # (later - earlier, the metric's unit)
    changes: tuple[Decimal, ...]  # later / earlier - 1
    ratios: tuple[Decimal, ...]  # later / earlier
    money: tuple[tuple[Decimal, str], ...] = ()  # (a cited money value, its currency)


def money_by_id(pack: Mapping[str, Any]) -> dict[str, tuple[str, list[Decimal]]]:
    """The money a card may cite, with its currency, by pack id: metric and kill-metric values whose unit is a
    currency code, fact values in usd or usd_per_year (in the fact's `currency`, else USD), insider trade values."""
    out: dict[str, tuple[str, list[Decimal]]] = {}
    for section in ("metrics", "ownership", "kill_metrics"):
        for i in pack.get(section) or []:
            unit = str(i.get("unit") or "").lower()
            if re.fullmatch(r"[a-z]{3}", unit) and unit not in NOT_MONEY and i.get("value") is not None:
                out[str(i["id"])] = (unit, [Decimal(str(i["value"]))])
    for f in pack.get("facts") or []:
        if str(f.get("unit") or "") in MONEY_FACT_UNITS:
            amounts = [Decimal(str(f[k])) for k in ("value", "value_low", "value_high") if f.get(k) is not None]
            out[str(f["id"])] = (str(f.get("currency") or "usd").lower(), amounts)
    for e in pack.get("insiders") or []:
        if e.get("value") is not None:
            out[str(e["id"])] = (str(e.get("currency") or "usd").lower(), [Decimal(str(e["value"]))])
    return out


def _series(cited: Sequence[str], values: Mapping[str, list[Decimal]]) -> dict[str, list[tuple[date, Decimal]]]:
    """The cited periods of each metric, in date order."""
    series: dict[str, set[tuple[date, Decimal]]] = {}
    for c in cited:
        m = METRIC_ID.match(c)
        if m and values.get(c):
            series.setdefault(m.group("metric"), set()).add((date.fromisoformat(m.group("end")), values[c][0]))
    return {metric: sorted(pts) for metric, pts in series.items()}


def candidates(
    cited: Sequence[str],
    values: Mapping[str, list[Decimal]],
    units: Mapping[str, str],
    money: Mapping[str, tuple[str, list[Decimal]]] | None = None,
) -> Candidates:
    raw = tuple((x, units.get(c) == "percent") for c in cited for x in values.get(c) or [])
    diffs: list[tuple[Decimal, str]] = []
    changes: list[Decimal] = []
    ratios: list[Decimal] = []
    for metric, pts in _series(cited, values).items():
        unit = next((units.get(c, "") for c in cited if c.startswith(f"m:{metric}:")), "")
        for i, (_, a) in enumerate(pts):
            for _, b in pts[i + 1 :]:
                diffs.append((b - a, unit))
                if a != 0:
                    changes.append(b / a - 1)
                    ratios.append(b / a)
    cash = money or {}
    held = tuple((x, cash[c][0]) for c in cited if c in cash for x in cash[c][1])
    return Candidates(raw, tuple(diffs), tuple(changes), tuple(ratios), held)


def number_ok(p: numbers.Parsed, c: Candidates, direction: int = 1) -> bool:
    """The written figure, with its sign, equals a candidate within the rounding of the digits written."""
    if p.unit == "percent":
        n = p.numeral * direction
        pcts = [x * 100 for x, _ in c.raw] + [x for x, is_pct in c.raw if is_pct]
        pcts += [x * 100 for x in (*c.changes, *c.ratios)]
        pcts += [d * 100 if u == "ratio" else d for d, u in c.differences if u in ("ratio", "percent")]
        return any(abs(n - x) <= p.tol for x in pcts)
    v = p.value * direction
    if p.currency is not None:  # "$1.25 billion" is cited money in dollars, not rupees or a share count (R3-F3)
        cash = [x for x, cur in c.money if cur == p.currency] + [d for d, u in c.differences if u == p.currency]
        return any(abs(v - x) <= p.tol * p.scale for x in cash)
    plain = [x for x, _ in c.raw] + [d for d, _ in c.differences] + list(c.ratios)
    return any(abs(v - x) <= p.tol * p.scale for x in plain)


def _period_of(p: numbers.Parsed, cited: Sequence[str], values: Mapping[str, list[Decimal]]) -> tuple[str, date] | None:
    for c in cited:
        m = METRIC_ID.match(c)
        if m and any(abs(p.value - x) <= p.tol * p.scale for x in values.get(c) or []):
            return m.group("metric"), date.fromisoformat(m.group("end"))
    return None


def direction_errors(text: str, cited: Sequence[str], values: Mapping[str, list[Decimal]],
                     years: tuple[int, int] = (1900, 2100)) -> list[str]:  # fmt: skip
    """A move between two cited periods of one metric runs from the earlier period to the later one, and its words
    match it (M6 review R1-F3, R2-F2, R3-F1): "rose to X from Y", "fell from Y to X", "X, down from Y" and "X versus
    Y" (X the later level unless the words mark it as the earlier one); "fell to X" alone, when X is a cited period
    of a metric with another cited period before it, against that one."""
    masked, nums = _figures(text, years)
    out: list[str] = []
    paired: set[int] = set()
    for a, b in zip(nums, nums[1:], strict=False):
        before, between = masked[: a.start], masked[a.end : b.start]
        wa, wb = masked[a.start : a.end].strip(), masked[b.start : b.end].strip()
        if TO_FROM.search(before) and FROM_.match(between):
            later, earlier, written, word = a, b, f"to {wa} from {wb}", _governing(before)
        elif FROM_TO.search(before) and TO_.match(between):
            later, earlier, written, word = b, a, f"from {wa} to {wb}", _governing(before)
        elif m := UP_DOWN_FROM.match(between):
            later, earlier, written = a, b, f"{wa}, {'up' if m.group('up') else 'down'} from {wb}"
            word = 1 if m.group("up") else -1
        elif m := VERSUS.match(between):
            later, earlier = (b, a) if EARLIER.search(m.group("fill")) else (a, b)
            written, word = f"{wa} versus {wb}", _governing(before) if TO_FROM.search(before) else 0
        else:
            continue
        paired |= {a.start, b.start}
        pl, pe = _period_of(later, cited, values), _period_of(earlier, cited, values)
        if pl and pe and pl[0] == pe[0] and pl[1] < pe[1]:
            out.append(f"'{written}': the move runs from {pe[1]} back to {pl[1]}; the later period is the level it "
                       "reaches")  # fmt: skip
        if word and (later.value - earlier.value) * word < 0:
            out.append(f"'{written}': the words say the opposite of the move")
    series = _series(cited, values)
    for x in nums:
        before = masked[: x.start]
        if x.start in paired or not TO_FROM.search(before):
            continue
        word, period = _governing(before), _period_of(x, cited, values)
        pts = series.get(period[0], []) if period else []
        if not word or period is None or len(pts) < 2:
            continue
        i = next(k for k, (d, _) in enumerate(pts) if d == period[1])
        written = f"to {masked[x.start : x.end].strip()}"
        if i == 0:
            out.append(f"'{written}': the move into {period[1]} starts from a period that isn't cited (the earliest "
                       f"cited {period[0]} is {period[1]})")  # fmt: skip
        elif (x.value - pts[i - 1][1]) * word < 0:
            out.append(f"'{written}': the words say the opposite of the move from {pts[i - 1][0]} to {period[1]}")
    return out


def _multiple(word: str) -> float:
    w = re.sub(r"\s+", " ", word.lower())
    if w.startswith("doubl"):
        return 2.0
    if w.startswith("tripl"):
        return 3.0
    if w.startswith("quadrupl"):
        return 4.0
    if w.startswith("halv") or w == "cut in half":
        return 0.5
    fold = re.match(r"(\w+?)[- ]?fold$", w)
    if fold:
        n = fold.group(1)
        return float(FOLD[n]) if n in FOLD else float(n)
    part = next(v for k, v in FRACTION.items() if w.endswith(k))
    return 1 - part if re.match(r"(?:down|fell|declined|dropped|cut|shrank|slid)\b", w) else 1 + part


def _says(ratio: Decimal, k: float, qualifier: str) -> bool:
    """Whether a ratio (later / earlier) is what the multiplier says: within 5% of it and within a tenth of the change
    it names ("by a third" is 1.30-1.37, not 1.28); "more than": at least it; "nearly": up to 15% short of it (for a
    fall, the mirror image)."""
    x = float(ratio)
    if qualifier.startswith("more"):
        return x >= k * 0.995 if k > 1 else x <= k * 1.005
    if qualifier:
        return k * 0.85 <= x <= k if k > 1 else k <= x <= k * 1.15
    return abs(x - k) <= min(0.05 * k, 0.1 * abs(k - 1))


def multiplier_errors(text: str, c: Candidates) -> list[str]:
    """ "doubled", "halved", "up by half", "threefold", "tenfold", "grew by a third": a ratio of two cited periods of
    one metric must say so (M6 review R2-F2, R3-F1)."""
    out = []
    for m in MULTIPLIER.finditer(_clean(text)):
        k, q = _multiple(m.group("w")), (m.group("q") or "").strip().lower()
        if not any(_says(r, k, q) for r in c.ratios):
            out.append(f"{m.group(0).strip()!r} matches no ratio of two cited periods of one metric")
    return out


def _opening_word(rest: str) -> bool:
    """Whether the text after an abbreviation's period starts with a capitalised word that opens sentences."""
    m = re.match(r"([A-Za-z]+)(?=[\s,])", rest.lstrip().lstrip(OPENERS))
    return m is not None and m.group(1)[0].isupper() and m.group(1).lower() in OPENING


def _boundary(line: str, start: int, m: re.Match[str]) -> bool:
    """Whether the end mark `m` ends a sentence: it is followed by the end of the line, by a space or an opening
    bracket or quote, or by a capital ("$1.87", "e.g.," and "3.5x" run on; so do "U.S." and "J.P."). After a period,
    RUN_ON words never end one, abbreviations and dotted initials (N.V., E.U.) end one only before a word in OPENING,
    and an initial after a capitalised word ("John A. Smith") doesn't; an ellipsis ends one before a capital (M6
    review R1-F2, R2-F1, R3-F2)."""
    rest = line[m.end() :]
    if not rest:
        return True
    mark = m.group(0)
    period = mark.startswith(".")
    seg = line[start : m.start()]
    word = re.search(r"([A-Za-z][A-Za-z.]*)$", seg)
    w = (word.group(1) if word else "").lower().rstrip(".")
    if not (rest[0].isspace() or rest[0] in OPENERS):
        if not rest[0].isupper():
            return False
        return not (period and re.fullmatch(r"[a-z]", w) and re.match(r"[A-Za-z]\.", rest))  # "U.S", "J.P."
    if mark.startswith("…"):
        return rest.lstrip().lstrip(OPENERS)[:1].isupper()  # "servers… A provider" ends; "grow… over time" doesn't
    if not period:
        return True
    if w in RUN_ON:
        return False
    if w in ABBREVIATIONS or re.fullmatch(r"(?:[a-z]\.)+[a-z]", w):
        return _opening_word(rest)
    if re.fullmatch(r"[a-z]", w):
        prev = re.search(r"([A-Za-z]+)\W+[A-Za-z]$", seg)
        return prev is not None and not prev.group(1)[0].isupper()  # "plan b. The" ends; "John A. Smith" doesn't
    return True


def _sentences(text: str) -> list[str]:
    """Sentences covering all of `text` (any line break ends one; a segment of citations alone joins the sentence
    before it)."""
    parts: list[str] = []
    for line in LINE_BREAK.split(text):
        start = 0
        for m in END.finditer(line):
            if _boundary(line, start, m):
                parts.append(line[start : m.end()])
                start = m.end()
        parts.append(line[start:])
    out: list[str] = []
    for part in parts:
        if out and part.strip() and not CITATION.sub("", part).strip():
            out[-1] += part
        elif part.strip():
            out.append(part)
    return [x.strip() for x in out]


def _fold(text: str) -> str:
    t = text.lower().translate({0x2019: "'", 0x2018: "'", 0x02BC: "'", 0x60: "'"})
    t = re.sub(r"[\u2010-\u2015\-]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _strings(x: Any) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, Mapping):
        return [s for v in x.values() for s in _strings(v)]
    if isinstance(x, list | tuple):
        return [s for v in x for s in _strings(v)]
    return []


def _hype(card: Mapping[str, Any], words: Sequence[str]) -> list[str]:
    """Hype words after folding case, apostrophes, hyphens and spacing; a word also matches when the text splits or
    hyphenates it ("multi-bagger", "multi bagger")."""
    text = _fold(" ".join(_strings(card)))
    tokens = text.split(" ")
    found = []
    for w in words:
        fw = _fold(w)
        compact = fw.replace(" ", "")
        joined = any("".join(tokens[i : i + n]).startswith(compact) for i in range(len(tokens)) for n in (1, 2, 3))
        if re.search(r"(?<!\w)" + re.escape(fw), text) or joined:
            found.append(w)
    return found


def validate(
    card_doc: Mapping[str, Any],
    pack: Mapping[str, Any],
    hype: Sequence[str],
    router: Router | None = None,
) -> Result:
    r = Result(ok=True)
    try:
        EvidencePack.model_validate(pack)  # the pack itself first: extra or mistyped fields fail (M6 review R1-F4)
    except ValidationError as e:
        r.errors += [f"pack: {'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]
        r.ok = False
        return r
    try:
        card = Card.model_validate(card_doc)
    except ValidationError as e:
        r.errors += [f"schema: {'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]
        r.ok = False
        return r
    values = values_by_id(pack)
    units = units_by_id(pack)
    money = money_by_id(pack)
    ids = set(values)
    year = date.fromisoformat(str(pack["week_end"])).year
    years = (year - 30, year + 15)  # a bare four-digit number can be a year only in this range
    quotes = {str(f["id"]): str(f["quote"]) for f in pack.get("facts") or []}

    for section, items in (("facts", card.facts), ("why_mispriced", card.why_mispriced)):
        for i, item in enumerate(items):
            where = f"{section}[{i}]"
            errors: list[str] = []
            cited = list(dict.fromkeys([*item.cites, *CITE.findall(item.text)]))
            unknown = [c for c in cited if c not in ids]
            if unknown:
                errors.append(f"{where}: cites ids not in the pack: {unknown}")
            sentences = _sentences(item.text)
            for s in sentences:
                if not CITE.search(s) and not (len(sentences) == 1 and item.cites):
                    errors.append(f"{where}: sentence cites no pack id: {s!r}")
            known = [c for c in cited if c in ids]
            cands = candidates(known, values, units, money)
            masked, nums = _figures(item.text, years)
            for p in nums:
                if not number_ok(p, cands, sign(masked, p)):
                    written = item.text[p.start : p.end]
                    errors.append(f"{where}: number {written!r} matches no cited pack value or delta")
            errors += [f"{where}: {e}" for e in direction_errors(item.text, known, values, years)]
            errors += [f"{where}: {e}" for e in multiplier_errors(item.text, cands)]
            r.errors += errors
            if not errors and known and router is not None:  # every item the code passes (M6 review R3-F1)
                _claim_support(r, where, item.text, known, quotes, _computed(known, pack, values), router)
    if router is None:
        r.warnings.append("claim support (P-05) not checked: no provider (thesis-ingest.yml checks again)")
    for i, item in enumerate(card.risks):
        unknown = [c for c in [*item.cites, *CITE.findall(item.text)] if c not in ids]
        if unknown:
            r.errors.append(f"risks[{i}]: cites ids not in the pack: {unknown}")

    for section, label in (("inferences", "Inference:"), ("assumptions", "Assumption:")):
        for i, text in enumerate(getattr(card, section)):
            if not text.startswith(label):
                r.errors.append(f"{section}[{i}]: does not start with {label!r}")
            for p in sentence_numbers(text, years):
                if not ASSUMED.match(text[p.end :]):
                    r.errors.append(f"{section}[{i}]: number {text[p.start : p.end]!r} is not marked (assumed)")

    _kill_criteria(r, card, pack, values)
    for w in _hype(card_doc, hype):
        r.errors.append(f"hype word: {w!r}")
    r.ok = not r.errors
    return r


def _kill_criteria(r: Result, card: Card, pack: Mapping[str, Any], values: Mapping[str, list[Decimal]]) -> None:
    window = pack.get("next_filing") or {}
    after = date.fromisoformat(str(window.get("closes") or pack["week_end"]))
    kill_ids = {str(k["id"]) for k in pack.get("kill_metrics") or []}
    for i, k in enumerate(card.kill_criteria):
        where = f"kill_criteria[{i}]"
        if k.metric_id not in kill_ids or not is_kill_metric(k.metric_id):
            r.errors.append(f"{where}: {k.metric_id!r} is not a kill-criteria metric of the pack")
            continue
        now = next(iter(values.get(k.metric_id) or []), None)
        if now is None:
            r.errors.append(f"{where}: {k.metric_id} has no value in the pack, so it can't be watched")
        if k.operator == "changes":
            if k.threshold is not None:
                r.errors.append(f"{where}: `changes` takes no threshold")
        elif k.threshold is None:
            r.errors.append(f"{where}: operator {k.operator} needs a threshold")
        elif now is not None and met(now, k.operator, k.threshold):
            r.errors.append(f"{where}: already met by the pack value {now} ({k.metric_id} {k.operator} {k.threshold})")
        if k.check_after <= after:
            r.errors.append(f"{where}: check_after {k.check_after} is not after the next filing window ({after})")


def met(value: Decimal, operator: str, threshold: Decimal | None, baseline: Decimal | None = None) -> bool:
    """Whether a kill criterion's condition holds (`changes`: the value differs from the baseline)."""
    if operator == "changes":
        return baseline is not None and value != baseline
    assert threshold is not None
    return {"<": value < threshold, "<=": value <= threshold, ">": value > threshold, ">=": value >= threshold,
            "==": value == threshold}[operator]  # fmt: skip


def _computed(cited: Sequence[str], pack: Mapping[str, Any], values: Mapping[str, list[Decimal]]) -> tuple[str, ...]:
    """What P-05 compares a sentence with besides the quotes: each cited item with its labels (a metric's name,
    period and unit; a fact's type, subject and currency; a signal's strength and named inputs), and the moves
    between cited periods of one metric, so a figure attributed to the wrong item, period or size shows (M6 review
    R3-F1)."""
    items = {str(i["id"]): i for s in SECTIONS for i in pack.get(s) or []}
    out = []
    for c in cited:
        item = items.get(c)
        if item is not None:
            shown = {k: v for k, v in item.items() if k not in NOT_FOR_P05 and v not in (None, "", [], {})}
            out.append(f"{c}: {json.dumps(shown, default=str, ensure_ascii=False, sort_keys=True)}")
    for metric, pts in _series(cited, values).items():
        for (d0, a), (d1, b) in zip(pts, pts[1:], strict=False):
            if a != 0:
                out.append(f"{metric} from {d0} to {d1}: difference {b - a}, change {b / a - 1:.4f}, ratio {b / a:.4f}")
    return tuple(out)


def _claim_support(r: Result, where: str, sentence: str, cited: Sequence[str], quotes: Mapping[str, str],
                   computed: tuple[str, ...], router: Router) -> None:  # fmt: skip
    qs = tuple(quotes[c] for c in cited if c in quotes)
    plain = re.sub(r"\s+([.,;:!?])", r"\1", CITE.sub("", sentence)).strip()
    answer = router.call(ClaimInput(plain, qs, computed))
    if isinstance(answer, Deferred):
        r.warnings.append(f"{where}: claim support (P-05) not checked: {answer.reason}")
        return
    if not bool(answer.content.get("supported")):
        parts = answer.content.get("unsupported_parts") or []
        r.errors.append(f"{where}: P-05 finds it unsupported: {parts} ({answer.content.get('reason', '')})")


# ---------------------------------------------------------------- files


def queue_path(week: str, root: Path = REPO_ROOT) -> Path:
    return root / "data" / "thesis_queue" / f"{week}.json"


def cards_dir(week: str, root: Path = REPO_ROOT) -> Path:
    return root / "data" / "thesis_cards" / week


def packs_of(week: str, root: Path = REPO_ROOT) -> dict[str, dict[str, Any]]:
    doc = json.loads(queue_path(week, root).read_text(encoding="utf-8"))
    return {str(p["company"]["key"]): p for p in doc.get("packs") or []}


def validate_week(week: str, root: Path = REPO_ROOT, router: Router | None = None) -> dict[str, Result]:
    packs = packs_of(week, root)
    words = hype_words(root)
    out: dict[str, Result] = {}
    for path in sorted(cards_dir(week, root).glob("*.json")):
        pack = packs.get(path.stem)
        if pack is None:
            out[path.name] = Result(False, [f"no pack for {path.stem} in {queue_path(week, root).name}"])
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, InvalidOperation) as e:
            out[path.name] = Result(False, [f"not JSON: {e}"])
            continue
        out[path.name] = validate(doc, pack, words, router)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, help="ISO week, e.g. 2026-W38")
    a = ap.parse_args(argv)
    if not queue_path(a.week).exists():
        print(f"thesis-validate {a.week}: no queue file {queue_path(a.week)} (the weekly thesis job writes it)")
        return 1
    results = validate_week(a.week, router=None)
    if not results:
        print(f"thesis-validate {a.week}: no cards in {cards_dir(a.week)}")
        return 0
    for name, res in results.items():
        print(f"{'OK  ' if res.ok else 'FAIL'} {name}")
        for e in res.errors:
            print(f"     error: {e}")
        for w in res.warnings:
            print(f"     note: {w}")
    failed = [n for n, res in results.items() if not res.ok]
    print(f"thesis-validate {a.week}: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

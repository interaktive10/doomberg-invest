"""Thesis-card validation (BRIEF §4.9): a card is rejected if any rule fails.

1. The pack is a valid EvidencePack (extra or mistyped fields fail; M6 review R1-F4), and the card follows the P-04
   schema (field types and counts; summary <= 60 words).
2. Every sentence in `facts` and `why_mispriced` cites >= 1 pack id: inline ([m:...], [f:...], [s:...], [c:...]) or,
   for a one-sentence item, in its `cites`; every cited id (there and in `risks`) exists in the pack. Sentences
   cover the whole text: a line break, or ., ! or ? followed by a space or a capital, ends one, except after an
   abbreviation (Corp., Inc., U.S.) or inside a number ($1.87) (M6 review R1-F2).
3. Every number in those sentences (digits, or number words with a unit: "fifty percent") equals, with its sign, a
   value under a cited id, or a delta computed by code between two cited periods of the same metric (later minus
   earlier, change, ratio), within the rounding of the digits written. A percent compares with a value x 100, and
   with the raw value only when the item's unit is percent. Direction words give the sign ("down 21.6%", "a loss of $50
   million"), and "to X from Y" must run from the earlier period to the later one (M6 review R1-F3). Years (four
   digits alone), dates (2026-06-30, June 30, 2026), fiscal labels (FY2026, Q2) and form names (10-Q, Item 2.01)
   are labels, not numbers; only [m:...]-style citations are removed, any other bracketed text is checked.
4. `inferences` start with "Inference:" and `assumptions` with "Assumption:"; a number there is followed by
   "(assumed)".
5. Kill criteria: a kill-criteria metric id of the pack with a value, an operator, a threshold (null only for
   `changes`) the pack value doesn't already meet, and a check_after date after the next filing window.
6. No hype word (config/terms.yaml `hype`) anywhere in the card, after folding case, apostrophes, hyphens and spacing
   ("can’t lose", "multi-bagger", "sure-shot", "to the  moon"; M6 review R1-F11).
7. P-05 (claim support) for a fact or why-mispriced sentence without numbers, when a router is given: unsupported ->
   rejected; no provider -> a warning (thesis-ingest.yml, which has the keys, checks again).

`python -m pipeline.thesis.validate --week 2026-W38` checks data/thesis_cards/<week>/*.json against the packs in
data/thesis_queue/<week>.json (exit 1 when a card fails).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
    r"|\b(?:FY|CY|Q[1-4]|H[12])\s?'?\d{2,4}(?:\s?[-\u2013/]\s?'?\d{2,4})?\b|\b(?:Q[1-4]|H[12]|[1-4]Q|[12]H)\b"
    r"|\b(?:10-K|10-Q|8-K|20-F|40-F|6-K|S-1|13F|13D|13G|DEF\s?14A|Form\s\d+[A-Z]?)\b"  # form names
    r"|\bItem\s\d+(?:\.\d+)?[A-Z]?\b"  # 8-K / 10-K items
    r"|\b[A-Z]{1,2}\d{1,2}\b",  # signal, flag and context names (S1, R4, C2, L3)
    re.I,
)
END = re.compile(r"[.!?]+[\"'\u201d\u2019)\]]*")
ABBREVIATIONS = frozenset(
    "inc corp co ltd llc plc lp no nos vs mr mrs ms dr st jr sr approx est dept fig e.g i.e etc u.s u.k u.n "
    "jan feb mar apr jun jul aug sep sept oct nov dec a.m p.m".split()
)
METRIC_ID = re.compile(r"^m:(?P<metric>[a-z0-9_]+):(?P<end>\d{4}-\d{2}-\d{2})$")
DOWN = re.compile(
    r"\b(?:down|fell|falls?|fallen|declined?|declines|decreased?|decreases|dropped|drops?|lower|shrank|shrinks?|"
    r"contracted|slipped|lost|loss\s+of|losses\s+of|deficit\s+of|outflows?\s+of|decline\s+of|decrease\s+of|"
    r"drop\s+of|fall\s+of|reduction\s+of|cut\s+of|negative)\s+(?:by\s+)?(?:about\s+|approximately\s+|"
    r"roughly\s+|nearly\s+|almost\s+|some\s+|over\s+|more\s+than\s+)?[$\u20b9]?$",
    re.I,
)
FOLLOW_DOWN = re.compile(
    r"^\s*(?:below|lower\s+than|less\s+than|under)\s+(?:a\s+year\s+(?:earlier|ago|before)|last\s+year|the\s+(?:prior|"
    r"previous|year[- ]earlier))",
    re.I,
)
UP_VERB = re.compile(r"\b(?:rose|rises?|risen|grew|grows?|grown|increased?|increases|climbed|jumped|gained|"
                     r"expanded)\b", re.I)  # fmt: skip
DOWN_VERB = re.compile(r"\b(?:fell|falls?|fallen|declined?|declines|decreased?|decreases|dropped|drops?|slipped|shrank|"
                       r"contracted)\b", re.I)  # fmt: skip
TO_FROM = re.compile(r"\bto\s+(?:about\s+|approximately\s+|roughly\s+)?(?:US\$|\$|\u20b9|Rs\.?\s?|INR\s?)?$", re.I)
FROM_ = re.compile(r"^[^.;\d]{0,60}?\bfrom\s+(?:about\s+|approximately\s+|roughly\s+)?(?:US\$|\$|\u20b9|Rs\.?\s?|"
                   r"INR\s?)?$", re.I)  # fmt: skip
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


def _clean(text: str) -> str:
    return LABELS.sub(lambda m: " " * len(m.group(0)), text)


def sentence_numbers(text: str) -> list[numbers.Parsed]:
    """The figures in a sentence, labels left out: numbers written with digits, and number words with a unit, currency
    or scale ("fifty percent"; "one of the two largest" is not a figure). A four-digit number alone is a year (not
    "2,000", "2000th" or "2000 MW")."""
    clean = _clean(text)
    out = []
    for p in numbers.parse(clean):
        written = clean[p.start : p.end]
        if not any(ch.isdigit() for ch in written):
            if p.unit is not None or p.currency is not None or p.scale_word is not None:
                out.append(p)  # "fifty percent", "two billion dollars", "three gigawatts": figures
            continue  # "one of the two largest": left to P-05 with the sentence
        four = re.fullmatch(r"\d{4}", written) is not None
        ordinal = re.match(r"(?:st|nd|rd|th)\b", clean[p.end : p.end + 3], re.I) is not None
        if four and not ordinal and 1900 <= p.numeral <= 2100:
            continue
        out.append(p)
    return out


def sign(text: str, p: numbers.Parsed) -> int:
    """-1 when the words say the figure is a fall or a loss ("down 21.6%", "a loss of $50 million", "3% below a
    year earlier", "-3.3%"), else +1."""
    before, after = text[: p.start], text[p.end :]
    if DOWN.search(before) or FOLLOW_DOWN.match(after) or re.search(r"(?<![\w.])[-\u2212]\s?[$\u20b9]?$", before):
        return -1
    return 1


@dataclass(frozen=True)
class Candidates:
    """What a cited figure may equal: the cited values (with whether the item's unit is percent), and the deltas
    between two cited periods of one metric, later against earlier (difference, change, ratio)."""

    raw: tuple[tuple[Decimal, bool], ...]
    differences: tuple[tuple[Decimal, str], ...]  # (later - earlier, the metric's unit)
    changes: tuple[Decimal, ...]  # later / earlier - 1
    ratios: tuple[Decimal, ...]  # later / earlier


def candidates(cited: Sequence[str], values: Mapping[str, list[Decimal]], units: Mapping[str, str]) -> Candidates:
    raw = tuple((x, units.get(c) == "percent") for c in cited for x in values.get(c) or [])
    series: dict[str, list[tuple[date, Decimal]]] = {}
    for c in cited:
        m = METRIC_ID.match(c)
        if m and values.get(c):
            series.setdefault(m.group("metric"), []).append((date.fromisoformat(m.group("end")), values[c][0]))
    diffs: list[tuple[Decimal, str]] = []
    changes: list[Decimal] = []
    ratios: list[Decimal] = []
    for metric, pts in series.items():
        unit = next((units.get(c, "") for c in cited if c.startswith(f"m:{metric}:")), "")
        pts = sorted(set(pts))
        for i, (_, a) in enumerate(pts):
            for _, b in pts[i + 1 :]:
                diffs.append((b - a, unit))
                if a != 0:
                    changes.append(b / a - 1)
                    ratios.append(b / a)
    return Candidates(raw, tuple(diffs), tuple(changes), tuple(ratios))


def number_ok(p: numbers.Parsed, c: Candidates, direction: int = 1) -> bool:
    """The written figure, with its sign, equals a candidate within the rounding of the digits written."""
    if p.unit == "percent":
        n = p.numeral * direction
        pcts = [x * 100 for x, _ in c.raw] + [x for x, is_pct in c.raw if is_pct]
        pcts += [x * 100 for x in (*c.changes, *c.ratios)]
        pcts += [d * 100 if u == "ratio" else d for d, u in c.differences if u in ("ratio", "percent")]
        return any(abs(n - x) <= p.tol for x in pcts)
    v = p.value * direction
    plain = [x for x, _ in c.raw] + [d for d, _ in c.differences] + list(c.ratios)
    return any(abs(v - x) <= p.tol * p.scale for x in plain)


def _period_of(p: numbers.Parsed, cited: Sequence[str], values: Mapping[str, list[Decimal]]) -> tuple[str, date] | None:
    for c in cited:
        m = METRIC_ID.match(c)
        if m and any(abs(p.value - x) <= p.tol * p.scale for x in values.get(c) or []):
            return m.group("metric"), date.fromisoformat(m.group("end"))
    return None


def direction_errors(text: str, cited: Sequence[str], values: Mapping[str, list[Decimal]]) -> list[str]:
    """ "rose to X from Y" / "fell to X from Y": X is the later period of the same metric, and the verb matches the
    move (M6 review R1-F3)."""
    clean = _clean(text)
    nums = [p for p in numbers.parse(clean) if any(ch.isdigit() for ch in clean[p.start : p.end])]
    out = []
    for x, y in zip(nums, nums[1:], strict=False):
        if not TO_FROM.search(clean[: x.start]) or not FROM_.match(clean[x.end : y.start]):
            continue
        px, py = _period_of(x, cited, values), _period_of(y, cited, values)
        written = f"{clean[x.start : x.end].strip()} from {clean[y.start : y.end].strip()}"
        if px and py and px[0] == py[0] and px[1] < py[1]:
            out.append(f"'to {written}': {clean[x.start : x.end].strip()} is the earlier period ({px[1]})")
        clause = clean[: x.start]
        if UP_VERB.search(clause[-60:]) and x.value < y.value or DOWN_VERB.search(clause[-60:]) and x.value > y.value:
            out.append(f"'to {written}': the verb says the opposite of the move")
    return out


# ---------------------------------------------------------------- the rules


def _sentences(text: str) -> list[str]:
    """Sentences covering all of `text` (a segment of citations alone joins the sentence before it)."""
    parts: list[str] = []
    for line in text.split("\n"):
        start = 0
        for m in END.finditer(line):
            nxt = line[m.end() : m.end() + 1]
            if nxt and not (nxt.isspace() or nxt.isupper()):
                continue  # "$1.87", "e.g.,", "3.5x"
            word = re.search(r"([A-Za-z][A-Za-z.]*)$", line[start : m.start()])
            w = (word.group(1) if word else "").lower().rstrip(".")
            if m.group(0).startswith(".") and (w in ABBREVIATIONS or re.fullmatch(r"(?:[a-z]\.)*[a-z]", w)):
                continue  # Corp., U.S., an initial
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
    ids = set(values)
    quotes = {str(f["id"]): str(f["quote"]) for f in pack.get("facts") or []}

    for section, items in (("facts", card.facts), ("why_mispriced", card.why_mispriced)):
        for i, item in enumerate(items):
            where = f"{section}[{i}]"
            cited = list(dict.fromkeys([*item.cites, *CITE.findall(item.text)]))
            unknown = [c for c in cited if c not in ids]
            if unknown:
                r.errors.append(f"{where}: cites ids not in the pack: {unknown}")
            sentences = _sentences(item.text)
            for s in sentences:
                if not CITE.search(s) and not (len(sentences) == 1 and item.cites):
                    r.errors.append(f"{where}: sentence cites no pack id: {s!r}")
            known = [c for c in cited if c in ids]
            cands = candidates(known, values, units)
            nums = sentence_numbers(item.text)
            for p in nums:
                if not number_ok(p, cands, sign(item.text, p)):
                    written = item.text[p.start : p.end]
                    r.errors.append(f"{where}: number {written!r} matches no cited pack value or delta")
            r.errors += [f"{where}: {e}" for e in direction_errors(item.text, known, values)]
            if not nums and known and router is not None:
                _claim_support(r, where, item.text, known, quotes, values, router)
            elif not nums and router is None:
                r.warnings.append(f"{where}: claim support (P-05) not checked: no provider")
    for i, item in enumerate(card.risks):
        unknown = [c for c in [*item.cites, *CITE.findall(item.text)] if c not in ids]
        if unknown:
            r.errors.append(f"risks[{i}]: cites ids not in the pack: {unknown}")

    for section, label in (("inferences", "Inference:"), ("assumptions", "Assumption:")):
        for i, text in enumerate(getattr(card, section)):
            if not text.startswith(label):
                r.errors.append(f"{section}[{i}]: does not start with {label!r}")
            for p in sentence_numbers(text):
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


def _claim_support(r: Result, where: str, sentence: str, cited: Sequence[str], quotes: Mapping[str, str],
                   values: Mapping[str, list[Decimal]], router: Router) -> None:  # fmt: skip
    qs = tuple(quotes[c] for c in cited if c in quotes)
    computed = tuple(f"{c} = {', '.join(str(v) for v in values[c][:6])}" for c in cited if c not in quotes)
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

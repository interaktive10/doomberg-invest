"""Thesis-card validation (BRIEF §4.9): a card is rejected if any rule fails.

1. The P-04 schema (field types and counts; summary <= 60 words).
2. Every sentence in `facts` and `why_mispriced` cites >= 1 pack id: inline ([m:...], [f:...], [s:...], [c:...]) or,
   for a one-sentence item, in its `cites`; every cited id (there and in `risks`) exists in the pack.
3. Every number in those sentences equals a value under a cited id, or a delta computed by code from two cited
   values (difference, ratio, change), within the rounding of the digits written; a percent compares with a ratio
   x 100 too. Years, dates, fiscal labels (FY2026, Q2) and form names (10-Q, Item 2.01) are labels, not numbers.
4. `inferences` start with "Inference:" and `assumptions` with "Assumption:"; a number there is followed by
   "(assumed)".
5. Kill criteria: a kill-criteria metric id of the pack with a value, an operator, a threshold (null only for
   `changes`) the pack value doesn't already meet, and a check_after date after the next filing window.
6. No hype word (config/terms.yaml `hype`) anywhere in the card.
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
from pipeline.thesis.evidence_pack import ClaimInput, is_kill_metric, values_by_id

CITE = re.compile(r"\[((?:m|f|s|c):[^\]\s]+)\]")
LABELS = re.compile(
    r"\[[^\]]*\]"  # citations
    r"|\b\d{4}-\d{2}-\d{2}\b"  # dates
    r"|\b(?:FY|CY|Q[1-4]|H[12])\s?'?\d{2,4}\b|\b(?:Q[1-4]|H[12])\b"  # fiscal labels
    r"|\b(?:10-K|10-Q|8-K|20-F|40-F|6-K|S-1|13F|13D|13G|DEF\s?14A|Form\s\d+[A-Z]?)\b"  # form names
    r"|\bItem\s\d+(?:\.\d+)?[A-Z]?\b"  # 8-K / 10-K items
    r"|\b[A-Z]{1,2}\d{1,2}\b",  # signal, flag and context names (S1, R4, C2, L3)
    re.I,
)
SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+(?=\s|$)|$)")
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


def sentence_numbers(text: str) -> list[numbers.Parsed]:
    """The numbers written with digits in a sentence, labels left out."""
    clean = LABELS.sub(lambda m: " " * len(m.group(0)), text)
    out = []
    for p in numbers.parse(clean):
        if not any(ch.isdigit() for ch in clean[p.start : p.end]):
            continue  # a number word ("one of"), not a figure
        year = p.decimals == 0 and 1900 <= p.numeral <= 2100 and p.currency is None and p.unit is None
        if year and p.scale_word is None:
            continue
        out.append(p)
    return out


def candidates(values: Sequence[Decimal]) -> list[Decimal]:
    """The cited values and the deltas code computes from them (difference, ratio, change)."""
    vals = list(dict.fromkeys(values))
    out = list(vals)
    for a in vals:
        for b in vals:
            if a is b or a == b:
                continue
            out.append(a - b)
            if b != 0:
                out += [a / b, a / b - 1]
    return out


def number_ok(p: numbers.Parsed, cands: Sequence[Decimal]) -> bool:
    for c in cands:
        ac = abs(c)
        if p.unit == "percent":
            if abs(p.numeral - ac * 100) <= p.tol or abs(p.numeral - ac) <= p.tol:
                return True
            continue
        if abs(p.value - ac) <= p.tol * p.scale or abs(p.numeral - ac) <= p.tol:
            return True
    return False


# ---------------------------------------------------------------- the rules


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.findall(text) if s.strip()]


def _hype(card: Mapping[str, Any], words: Sequence[str]) -> list[str]:
    text = json.dumps(card, ensure_ascii=False).lower()
    return [w for w in words if re.search(r"(?<!\w)" + re.escape(w.lower()), text)]


def validate(
    card_doc: Mapping[str, Any],
    pack: Mapping[str, Any],
    hype: Sequence[str],
    router: Router | None = None,
) -> Result:
    r = Result(ok=True)
    try:
        card = Card.model_validate(card_doc)
    except ValidationError as e:
        r.errors += [f"schema: {'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]
        r.ok = False
        return r
    values = values_by_id(pack)
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
            cands = candidates([v for c in known for v in values[c]])
            nums = sentence_numbers(item.text)
            for p in nums:
                if not number_ok(p, cands):
                    written = item.text[p.start : p.end]
                    r.errors.append(f"{where}: number {written!r} matches no cited pack value or delta")
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

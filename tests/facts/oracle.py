"""A mock P-01 provider for the F-SYN structure tests (M5-01 without cassettes).

It answers from the ground truth the way a good model would (each planted fact whose quote is in the chunk, numbers
as written, with the scale word) and adds the mistakes free models make, which Verify-1 must catch: a share
repurchase, dividend, EPS or stock-price sentence dressed up as a fact (V1-TYPE), a paraphrased quote (V1-QUOTE), a
wrong number (V1-NUM), a wrong unit (V1-UNIT) and a repeated fact (V1-DUP). Quotes come back with extra spaces, as
models often write them, to exercise the whitespace-insensitive grounding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pipeline.facts.ground import ground
from pipeline.llm.providers.base import Completion, Request


def chunk_text(req: Request) -> str:
    return req.user.split("<<<\n", 1)[1].rsplit("\n>>>", 1)[0]


def _num(s: str | None) -> float | int | None:
    if s is None:
        return None
    return int(s) if s.isdigit() else float(s)


def as_p01(p: dict[str, Any]) -> dict[str, Any]:
    w = p["written"]
    return {
        "fact_type": p["fact_type"], "subject": p["subject_key"].split(":", 1)[1].replace("_", " "),
        "subject_key": p["subject_key"], "value": _num(w.get("value")), "value_low": _num(w.get("value_low")),
        "value_high": _num(w.get("value_high")), "unit": p["unit"],
        "currency": p.get("currency") or ("USD" if p["unit"] in {"usd", "usd_per_year"} else None),
        "scale_word": w.get("scale_word"), "period_label": p.get("period_label"), "as_of": None,
        "counterparty": p.get("counterparty"), "location": None, "withdrawn": False,
        "quote": "  ".join(p["quote"].split(" ", 1)), "confidence": 0.9,
    }  # fmt: skip


NOISE = {
    "The Board authorized a new share repurchase program of up to $2.0 billion.": {
        "fact_type": "commitment_purchase", "subject": "share repurchase program", "value": 2.0, "unit": "usd",
        "scale_word": "billion", "subject_key": "purchase_obligations:total"},
    "We declared a quarterly dividend of $0.42 per share, payable next month.": {
        "fact_type": "price_increase", "subject": "quarterly dividend", "value": 0.42, "unit": "usd",
        "scale_word": None, "subject_key": "price_increase:dividend"},
    "Diluted earnings per share were $1.87, up 14% from a year ago.": {
        "fact_type": "capex_reported", "subject": "diluted EPS", "value": 1.87, "unit": "usd", "scale_word": None,
        "subject_key": "capex_reported:Q1FY2027"},
    "Our stock price rose 23% during the quarter, and two analysts upgraded their ratings to buy.": {
        "fact_type": "price_increase", "subject": "stock price", "value": 23, "unit": "percent", "scale_word": None,
        "subject_key": "price_increase:stock"},
}  # fmt: skip


@dataclass
class Oracle:
    truth: dict[str, Any]
    noise: bool = True
    name: str = "gemini"
    requests: list[Request] = field(default_factory=list)

    def available(self) -> bool:
        return True

    def complete(self, req: Request) -> Completion:
        self.requests.append(req)
        text = chunk_text(req)
        facts = []
        for d in self.truth["documents"]:
            for p in d["facts"]:
                if ground(p["quote"], text) is not None:
                    facts.append(as_p01(p))
        if self.noise:
            facts += self._noise(text, facts)
        return Completion({"facts": facts}, 500, 100)

    def _noise(self, text: str, facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for sentence, item in NOISE.items():
            if sentence in text:
                out.append({**item, "value_low": None, "value_high": None, "currency": "USD", "period_label": None,
                            "as_of": None, "counterparty": None, "location": None, "withdrawn": False,
                            "quote": sentence, "confidence": 0.8})  # fmt: skip
        for f in facts[:1]:
            out.append({**f, "quote": "Capital spending will roughly double as AI demand keeps growing."})  # V1-QUOTE
            if f["value"] is not None:
                out.append({**f, "value": f["value"] + 7})  # V1-NUM
                out.append({**f, "unit": "mwh"})  # V1-UNIT
            out.append(dict(f))  # V1-DUP
        return out

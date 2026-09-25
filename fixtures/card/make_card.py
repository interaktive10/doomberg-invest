"""F-CARD (BRIEF §9, M6-02): one evidence pack and six thesis cards for it, one good and five bad (an uncited fact,
a mismatched number, an unlabeled inference, an invalid kill criterion, a hype word). Each bad card differs from the
good one in exactly that respect. `python fixtures/card/make_card.py` rewrites the files (deterministic)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CID = "00000000-0000-4000-8000-00000000c0de"
F_CAPEX = "f:6f1c2a52-3b1e-4c43-9e59-3d1b1f0a0001"
F_ORDER = "f:6f1c2a52-3b1e-4c43-9e59-3d1b1f0a0002"
SEC = "https://www.sec.gov/Archives/edgar/data/999001/000099900126000102/ex991.htm"


def metric(name: str, end: str, value: str, unit: str = "usd") -> dict[str, Any]:
    return {"id": f"m:{name}:{end}", "name": name, "period_end": end, "value": value, "unit": unit,
            "source": "fundamentals"}  # fmt: skip


def kill(name: str, value: str, unit: str, description: str) -> dict[str, Any]:
    return {"id": f"m:{name}", "description": description, "value": value, "unit": unit}


PACK: dict[str, Any] = {
    "version": 1,
    "week": "2026-W38",
    "week_end": "2026-09-18",
    "company": {"company_id": CID, "key": "us-nmbs", "name": "Nimbus Compute Corp.", "market": "us", "ticker": "NMBS",
                "nse_symbol": None, "cik": "0000999001", "isin": None, "sector": "Information Technology",
                "industry": "Computer hardware", "capex_desk": True, "fiscal_year_end": "0630"},
    "bucket": "candidate",
    "families": ["fundamentals", "text"],
    "metrics": [metric("revenue", "2025-06-30", "980000000"), metric("revenue", "2026-06-30", "1250000000"),
                metric("op_income", "2026-06-30", "206250000"), metric("rpo", "2025-06-30", "2900000000"),
                metric("rpo", "2026-06-30", "4200000000"),
                metric("diluted_shares", "2026-06-30", "212000000", "shares")],
    "signals": [{"id": "s:S1", "kind": "signal", "fired": True, "strength": "0.82", "hard": None, "status": None,
                 "inputs": {"g_ob": 0.4483, "g_rev": 0.2755, "gap": 0.1728, "consecutive": 2}},
                {"id": "s:R2", "kind": "red_flag", "fired": False, "strength": None, "hard": False,
                 "status": "unknown", "inputs": {"missing": ["receivables_growth"]}}],
    "context": [{"id": "c:C2", "value": "0.06", "pct": None,
                 "inputs": {"g_implied": 0.12, "g_evidence": 0.18, "discount_rate": 0.09, "terminal_growth": 0.025}},
                {"id": "c:evidence", "value": "62.5", "pct": None, "inputs": {"families": ["fundamentals", "text"]}},
                {"id": "c:gap", "value": "58.3", "pct": None, "inputs": {}}],
    "facts": [{"id": F_CAPEX, "fact_type": "capex_guidance", "subject": "Fiscal 2027 capital expenditures",
               "subject_key": "capex_guidance:FY2027", "value": "1800000000", "value_low": None, "value_high": None,
               "unit": "usd", "currency": "USD", "period_label": "FY2027", "period_end": "2027-06-30",
               "as_of": "2026-08-06", "counterparty": None,
               "quote": "We expect fiscal 2027 capital expenditures of approximately $1.8 billion.", "url": SEC,
               "document_kind": "EX-99.1", "published_at": "2026-08-06T20:05:00Z"},
              {"id": F_ORDER, "fact_type": "order_win", "subject": "Multi-year hyperscaler order",
               "subject_key": "order_win:hyperscaler", "value": "600000000", "value_low": None, "value_high": None,
               "unit": "usd", "currency": "USD", "period_label": None, "period_end": None, "as_of": "2026-08-06",
               "counterparty": "a hyperscale cloud provider",
               "quote": "Nimbus received a $600 million multi-year order from a hyperscale cloud provider.",
               "url": SEC, "document_kind": "EX-99.1", "published_at": "2026-08-06T20:05:00Z"}],
    "ownership": [{"id": "m:inst_holders:2026-06-30", "name": "inst_holders", "period_end": "2026-06-30",
                   "value": "412", "unit": "count", "source": "sec_13f"}],
    "insiders": [],
    "capex_categories": ["compute"],
    "capex_links": [{"entity": "a hyperscale cloud provider", "entity_kind": "company", "relation": "customer",
                     "fact_id": F_ORDER}],
    "kill_metrics": [kill("revenue_ttm_yoy", "0.2410", "ratio", "TTM revenue vs the TTM a year earlier"),
                     kill("rpo_yoy", "0.4483", "ratio", "RPO vs a year earlier"),
                     kill("op_margin_ttm", "0.1650", "ratio", "TTM operating income / TTM revenue"),
                     kill("evidence", "62.5", "score", "Evidence score, latest scored week (0-100)"),
                     {"id": "m:signal:S1", "description": "S1 strength, latest scored week (0-1)", "value": "0.82",
                      "unit": "score"}],
    "next_filing": {"period_end": "2026-09-30", "form": "10-Q", "opens": "2026-10-01", "closes": "2026-11-14"},
}  # fmt: skip

GOOD: dict[str, Any] = {
    "summary": "Nimbus's order book is growing faster than its revenue, and the market price implies slower growth "
               "than the evidence supports. The thesis holds while backlog keeps converting and margins stay intact.",
    "facts": [
        {"text": "Revenue rose to $1.25 billion in the June 2026 quarter from $980 million a year earlier, up 27.6% "
                 "[m:revenue:2026-06-30] [m:revenue:2025-06-30].",
         "cites": ["m:revenue:2026-06-30", "m:revenue:2025-06-30"]},
        {"text": "Remaining performance obligations reached $4.2 billion, 44.8% above a year earlier "
                 "[m:rpo:2026-06-30] [m:rpo:2025-06-30].", "cites": ["m:rpo:2026-06-30", "m:rpo:2025-06-30"]},
        {"text": f"Management expects fiscal 2027 capital expenditures of approximately $1.8 billion [{F_CAPEX}].",
         "cites": [F_CAPEX]},
        {"text": f"A hyperscale cloud provider placed a $600 million multi-year order [{F_ORDER}].",
         "cites": [F_ORDER]},
        {"text": "The order-book signal S1 fired with strength 0.82 [s:S1].", "cites": ["s:S1"]},
    ],
    "why_mispriced": [
        {"text": "The price implies 12% annual growth, below the 18% the evidence supports [c:C2].",
         "cites": ["c:C2"]},
    ],
    "inferences": ["Inference: the order book growing faster than revenue suggests revenue growth can continue if "
                   "orders convert on the usual schedule."],
    "assumptions": ["Assumption: backlog converts to revenue within 24 months (assumed).",
                    "Assumption: the operating margin stays above 15% (assumed)."],
    "risks": [{"text": f"Customer concentration: one hyperscaler placed the largest disclosed order [{F_ORDER}].",
               "cites": [F_ORDER]},
              {"text": f"Heavy capital spending could strain free cash flow [{F_CAPEX}].", "cites": [F_CAPEX]}],
    "kill_criteria": [
        {"metric_id": "m:rpo_yoy", "operator": "<", "threshold": 0.1, "check_after": "2026-11-20",
         "why": "The thesis rests on the order book growing; under 10% a year it no longer leads revenue."},
        {"metric_id": "m:op_margin_ttm", "operator": "<", "threshold": 0.12, "check_after": "2026-11-20",
         "why": "Growth bought with falling margins is not the thesis."},
    ],
    "read_next": [{"title": "Nimbus press release with fiscal 2027 guidance", "url": SEC}],
}  # fmt: skip


def bad_cards() -> dict[str, tuple[dict[str, Any], str]]:
    """name -> (card, a substring of the error validate.py must report)."""
    out: dict[str, tuple[dict[str, Any], str]] = {}
    c = copy.deepcopy(GOOD)
    c["facts"][3] = {"text": "A hyperscale cloud provider placed a large multi-year order.", "cites": []}
    out["bad_uncited"] = (c, "sentence cites no pack id")
    c = copy.deepcopy(GOOD)
    c["facts"][0]["text"] = c["facts"][0]["text"].replace("$1.25 billion", "$1.35 billion")
    out["bad_number"] = (c, "number '1.35 billion' matches no cited pack value")
    c = copy.deepcopy(GOOD)
    c["inferences"] = ["The order book growing faster than revenue means revenue growth will continue."]
    out["bad_inference"] = (c, "does not start with 'Inference:'")
    c = copy.deepcopy(GOOD)
    c["kill_criteria"][0]["check_after"] = "2026-10-15"
    out["bad_kill"] = (c, "is not after the next filing window")
    c = copy.deepcopy(GOOD)
    c["summary"] = "A multibagger in the making: " + c["summary"]
    out["bad_hype"] = (c, "hype word: 'multibagger'")
    return out


def files() -> dict[str, str]:
    out = {"pack.json": json.dumps(PACK, indent=1) + "\n", "good.json": json.dumps(GOOD, indent=1) + "\n"}
    expected = {}
    for name, (card, error) in bad_cards().items():
        out[f"{name}.json"] = json.dumps(card, indent=1) + "\n"
        expected[name] = error
    out["expected.json"] = json.dumps(expected, indent=1) + "\n"
    return out


if __name__ == "__main__":
    for name, text in files().items():
        (HERE / name).write_text(text, encoding="utf-8")
    print(f"F-CARD: {len(files())} files in {HERE}")

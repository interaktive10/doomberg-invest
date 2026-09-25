"""Seed data for the web app's end-to-end tests (BRIEF §8 M7; CI job `web`, after the migrations on the local Supabase
stack). Five companies scored for the week ending 2026-09-18, one per bucket or so, and everything the screens show:
fundamentals, signals, red flags, context, a verified fact with its document, a counterparty link, a thesis card in
research with kill criteria, capex memberships waiting for a decision, the demand index, a brief, a digest, source
health, LLM use, Lab results and weights versions. Fixed ids (web/e2e/seed.ts has the same ones).

`python scripts/seed_e2e.py --database-url postgresql://...` (a fresh database: it inserts, it doesn't upsert).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from typing import Any

import psycopg

W = date(2026, 9, 18)
ECHO = "00000000-0000-4000-8000-0000000000e1"
KAPPA = "00000000-0000-4000-8000-0000000000e2"
DELTA = "00000000-0000-4000-8000-0000000000e3"
OMEGA = "00000000-0000-4000-8000-0000000000e4"
SIGMA = "00000000-0000-4000-8000-0000000000e5"
ECHO_THESIS = "00000000-0000-4000-8000-0000000000a1"
ECHO_DOC = "00000000-0000-4000-8000-0000000000d1"
ECHO_FACT = "00000000-0000-4000-8000-0000000000f1"
NIMBUS = "00000000-0000-4000-8000-0000000000b1"

COMPANIES = [
    # id, market, name, cik, ticker, nse_symbol, isin, sector, industry, fye, capex_desk
    (ECHO, "us", "Echo Grid Corp.", "0000999101", "ECHO", None, None, "Industrials", "Electrical Equipment", "1231",
     True),
    (KAPPA, "in", "Kappa Cables Ltd", None, None, "KAPPA", "INE999K01011", "Industrials", "Cables", "0331", True),
    (DELTA, "us", "Delta Power Inc.", "0000999103", "DLTP", None, None, "Utilities", "Power Producers", "1231", False),
    (OMEGA, "us", "Omega Systems Inc.", "0000999104", "OMGA", None, None, "Technology", "Servers", "1231", False),
    (SIGMA, "us", "Sigma Holdings Inc.", "0000999105", "SGMA", None, None, "Financials", "Holding Companies", "1231",
     False),
]  # fmt: skip

SCORES = [  # company, evidence, gap, families, bucket
    (ECHO, 72.5, 61.2, ["fundamentals", "text"], "candidate"),
    (KAPPA, 64.0, None, ["fundamentals", "text"], "candidate"),
    (DELTA, 58.0, 30.0, ["fundamentals", "behavior"], "early"),
    (OMEGA, 66.0, 12.0, ["fundamentals", "structural"], "priced_in"),
    (SIGMA, 40.0, None, ["fundamentals"], "excluded"),
]

CARD_MD = """# Echo Grid Corp. (ECHO) — 2026-W38

Grid equipment demand from data-center interconnects is showing up in backlog before it shows up in revenue.

## Facts
- Total backlog reached $13.2 billion at quarter end [f:00000000-0000-4000-8000-0000000000f1].
- Revenue was $1.20 billion in the quarter ended March 31, 2026 [m:revenue:2026-03-31].

## Why it may be mispriced
- The price implies 5% annual growth while the evidence supports 17% [c:C2].

## Inferences
- Inference: backlog converts to revenue over roughly two years.

## Assumptions
- Assumption: margins hold near 20% (assumed).
- Assumption: no large customer cancels.

## Risks
- A single hyperscale customer is a large share of orders [f:00000000-0000-4000-8000-0000000000f1].

## Kill criteria
| Metric | Condition | Check after | Why |
|---|---|---|---|
| `m:revenue_ttm_yoy` | < 0.05 | 2026-11-20 | Growth thesis fails if TTM revenue growth drops below 5% |
"""


def quarters() -> list[tuple[date, float]]:
    ends = [date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30),
            date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]  # fmt: skip
    return [(d, 800e6 + 60e6 * i) for i, d in enumerate(ends)]


def seed(conn: psycopg.Connection[Any]) -> None:
    x = conn.execute
    for c in COMPANIES:
        x("insert into companies (id, market, name, cik, ticker, nse_symbol, isin, sector, industry, fiscal_year_end, "
          "in_universe, capex_desk) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s)", c)  # fmt: skip
    for end, revenue in quarters():
        x("insert into fundamentals_q (company_id, period_end, fiscal_label, filed_at, revenue, op_income, net_income, "
          "pretax_income, tax_expense, cfo, capex, da, total_assets, cash, total_debt, equity, rpo, diluted_shares, "
          "shares_outstanding, currency, source) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
          "%s, %s, %s, %s, 'USD', 'sec_xbrl')",
          (ECHO, end, f"Q{(end.month - 1) // 3 + 1} {end.year}", end + timedelta(days=36), revenue, revenue * 0.2,
           revenue * 0.15, revenue * 0.19, revenue * 0.04, revenue * 0.22, revenue * 0.05, revenue * 0.03, 9e9, 1.1e9,
           2.0e9, 4.5e9, 10e9 + (end.year - 2024) * 1.6e9, 120e6, 119e6))  # fmt: skip
    for cid, ev, gap, fam, bucket in SCORES:
        x("insert into scores (company_id, week_end, evidence, gap, families, bucket, weights_version) values "
          "(%s, %s, %s, %s, %s, %s, 'v1')", (cid, W, ev, gap, fam, bucket))  # fmt: skip
        x("insert into company_metrics (company_id, week_end, metrics) values (%s, %s, %s)",
          (cid, W, json.dumps({"revenue_yoy": 0.276 if cid == ECHO else 0.08, "roic": 0.18, "opm": 0.2})))  # fmt: skip
    for cid, sid, strength in [(ECHO, "S1", 0.82), (ECHO, "S9", 0.4), (KAPPA, "S9", 0.4), (DELTA, "S3", 0.6)]:
        x("insert into signal_values (company_id, week_end, signal_id, fired, strength, inputs) values "
          "(%s, %s, %s, true, %s, '{}')", (cid, W, sid, strength))  # fmt: skip
        x("insert into signal_values (company_id, week_end, signal_id, fired, strength, inputs) values "
          "(%s, %s, %s, true, %s, '{}')", (cid, W - timedelta(days=7), sid, strength))  # fmt: skip
    x("insert into redflag_values (company_id, week_end, flag_id, hard, inputs) values "
      "(%s, %s, 'R1', true, '{\"status\": \"fired\"}'), (%s, %s, 'R5', false, '{\"status\": \"fired\"}')",
      (SIGMA, W, OMEGA, W))  # fmt: skip
    for k in range(5):
        week = W - timedelta(days=7 * (4 - k))
        x(
            "insert into context_values (company_id, week_end, metric_id, value, pct, inputs) values "
            "(%s, %s, 'C1', %s, %s, %s)",
            (ECHO, week, 3.2 - 0.1 * k, 45 - 2 * k, json.dumps({"score": 55 + 2 * k})),
        )
    c2 = {"score": 80, "g_star": 0.05, "g_e": 0.17, "margin": 0.2, "s2c": 1.5, "discount_rate": 0.09,
          "terminal_growth": 0.025}  # fmt: skip
    x("insert into context_values (company_id, week_end, metric_id, value, pct, inputs) values "
      "(%s, %s, 'C2', 0.12, null, %s), (%s, %s, 'C3', 0.31, 55, '{\"score\": 45}'), "
      "(%s, %s, 'C4', 12, 30, '{\"score\": 70}')", (ECHO, W, json.dumps(c2), ECHO, W, ECHO, W))  # fmt: skip

    quote = "Total backlog reached $13.2 billion at quarter end."
    x("insert into documents (id, company_id, kind, url, title, published_at, sha256, raw_path, status) values "
      "(%s, %s, '10-Q', 'https://www.sec.gov/Archives/edgar/data/999101/echo-10q.htm', 'Echo Grid 10-Q', "
      "'2026-08-05 12:00+00', %s, 'e2e/echo-10q.htm', 'extracted')", (ECHO_DOC, ECHO, "0" * 64))  # fmt: skip
    x("insert into facts (id, company_id, document_id, fact_type, subject, subject_key, value_num, unit, currency, "
      "scale_word, as_of, quote, char_start, char_end, extraction_model, confidence, verification_status) values "
      "(%s, %s, %s, 'backlog', 'backlog', 'backlog:total', 13200000000, 'usd', 'USD', 'billion', '2026-08-05', %s, "
      "0, %s, 'e2e', 0.90, 'verified')", (ECHO_FACT, ECHO, ECHO_DOC, quote, len(quote)))  # fmt: skip
    x("insert into entities (id, name, normalized, kind) values (%s, 'Nimbus Compute Corp.', 'nimbus compute', "
      "'company')", (NIMBUS,))  # fmt: skip
    x("insert into links (from_company_id, to_entity_id, relation, fact_id) values (%s, %s, 'customer', %s)",
      (ECHO, NIMBUS, ECHO_FACT))  # fmt: skip

    pack = {"version": 1, "week": "2026-W38", "week_end": str(W),
            "metrics": [{"id": "m:revenue:2026-03-31", "name": "revenue", "period_end": "2026-03-31",
                         "value": "1160000000", "unit": "usd", "source": "sec_xbrl"}],
            "next_filing": {"period_end": "2026-09-30", "form": "10-Q", "opens": "2026-10-01",
                            "closes": "2026-11-14"}}  # fmt: skip
    card = {"summary": "Grid equipment demand shows up in backlog first.",
            "facts": [{"text": quote, "cites": [f"f:{ECHO_FACT}"]}]}  # fmt: skip
    x("insert into theses (id, company_id, state, card_md, card_json, evidence_pack, author, validation, "
      "created_week) values (%s, %s, 'research', %s, %s, %s, 'routine', '{\"ok\": true}', %s)",
      (ECHO_THESIS, ECHO, CARD_MD, json.dumps(card), json.dumps(pack), W))  # fmt: skip
    x("insert into kill_criteria (thesis_id, metric, operator, threshold, check_after, status, last_value, "
      "last_checked, why) values (%s, 'm:revenue_ttm_yoy', '<', 0.05, '2026-11-20', 'ok', 0.24, %s, "
      "'Growth thesis fails if TTM revenue growth drops below 5%%')", (ECHO_THESIS, W))  # fmt: skip

    x("insert into capex_memberships (company_id, category, source, status, evidence, quote) values "
      "(%s, 'power_equipment', 'p06', 'proposed', 'Transformer and HV cable orders from US data-center developers', "
      "'Kappa Cables received an export order for HV cables for a US data center campus.')", (KAPPA,))  # fmt: skip
    x("insert into capex_memberships (company_id, category, source, status, evidence, decided_at) values "
      "(%s, 'grid', 'industry_map', 'confirmed', 'SIC 3612 (transformers)', '2026-09-01 00:00+00')",
      (ECHO,))  # fmt: skip
    x("insert into capex_index (category, week_end, value, direction, input_growth) values "
      "('grid', %s, 1.2, 'rising', 0.18), ('power_equipment', %s, 0.3, 'flat', 0.04)", (W, W))  # fmt: skip
    x("insert into capex_briefs (week_end, body_md) values (%s, %s)",
      (W, "### Demand index\n\n- grid: rising (+1.2σ)\n- power_equipment: flat (+0.3σ)\n"))  # fmt: skip

    digest = (
        "Week ending 2026-09-18. Research only: no orders, no price alerts.\n\n## New candidates\n\n"
        "1. **Echo Grid Corp.** (ECHO, US): families fundamentals, text · Evidence 72.5 · Gap 61.2\n\n"
        "## Source health\n\n| Source | Last success | Status |\n|---|---|---|\n| sec | 2026-09-18 06:00Z | ok |\n"
    )
    x("insert into digests (week_end, title, body_md) values (%s, 'Doomberg weekly — 2026-W38', %s)", (W, digest))
    x("insert into source_health (source, last_success, last_error, stale) values "
      "('sec', '2026-09-18 06:00+00', null, false), ('nse', '2026-09-18 06:00+00', null, false), "
      "('bse', '2026-08-01 06:00+00', null, false), ('stooq', null, 'stale: 13 downloads failed', true)")  # fmt: skip
    x("insert into llm_calls (prompt_id, provider, model, ok, tokens_in, tokens_out, error) values "
      "('P-01', 'gemini', 'gemini-flash', true, 1000, 200, null), "
      "('P-01', 'gemini', 'gemini-flash', false, null, null, 'gemini: 429'), "
      "('P-07', 'groq', 'llama', true, 300, 20, null)")  # fmt: skip
    for signal, horizon, period, n, mean, t in [("S1", 12, "in_sample", 1200, 0.021, 2.4),
                                                ("S1", 12, "out_of_sample", 400, 0.012, 1.1),
                                                ("EVIDENCE_D1", 12, "out_of_sample", 300, -0.01, -0.8),
                                                ("EVIDENCE_D10", 12, "out_of_sample", 300, 0.02, 1.3)]:  # fmt: skip
        x("insert into lab_results (signal_id, market, horizon_m, period, n, excess_mean, excess_median, hit_rate, "
          "p10, t_nw) values (%s, 'us', %s, %s, %s, %s, %s, 0.54, -0.2, %s)",
          (signal, horizon, period, n, mean, mean / 2, t))  # fmt: skip
    x(
        "insert into weights_versions (version, weights, reason, approved_by, approved_at) values "
        "('v1', '{\"evidence\": {}}', 'config/weights.yaml on main', 'human-approved', '2026-09-20 00:00+00'), "
        "('v2-lab', '{\"evidence\": {}}', 'Signal Lab §4.10.5 proposals: evidence.S1 1.0 -> 1.2', null, null)"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    a = ap.parse_args(argv)
    if not a.database_url:
        print("seed_e2e: pass --database-url or set DATABASE_URL", file=sys.stderr)
        return 2
    with psycopg.connect(a.database_url) as conn, conn.transaction():
        seed(conn)
    print(f"seed_e2e: {len(COMPANIES)} companies scored for {W}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

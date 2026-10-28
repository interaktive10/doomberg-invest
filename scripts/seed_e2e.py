"""Seed data for the web app's end-to-end tests (BRIEF §8 M7; CI job `web`, after the migrations on the local Supabase
stack). Seven companies scored for the week ending 2026-09-18, one per bucket or so (Watch has a US and an India name),
and everything the screens show: fundamentals, signals, red flags, context, verified facts with their documents, a
counterparty link, a thesis card in research with kill criteria and its company's chart series (company_series), a
thesis a kill criterion moved to Review, a closed thesis with journal entries and a post-mortem, ownership, insider and
event rows, capex memberships waiting for a decision, the demand index, a brief, a digest, source health, LLM use, Lab
results and weights versions.
Fixed ids (web/e2e/seed.ts has the same ones).

`python scripts/seed_e2e.py --database-url postgresql://...` (a fresh database: it inserts, it doesn't upsert).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.signals.series import Quarter, Series  # noqa: E402
from pipeline.signals.weekly import series_points  # noqa: E402

W = date(2026, 9, 18)
ECHO = "00000000-0000-4000-8000-0000000000e1"
KAPPA = "00000000-0000-4000-8000-0000000000e2"
DELTA = "00000000-0000-4000-8000-0000000000e3"
OMEGA = "00000000-0000-4000-8000-0000000000e4"
SIGMA = "00000000-0000-4000-8000-0000000000e5"
LUMEN = "00000000-0000-4000-8000-0000000000e6"  # Watch, US (docs/SPEC_ISSUES.md 56)
TARA = "00000000-0000-4000-8000-0000000000e7"  # Watch, India
ECHO_THESIS = "00000000-0000-4000-8000-0000000000a1"
OMEGA_THESIS = "00000000-0000-4000-8000-0000000000a2"  # in Review: a kill criterion triggered, no new quarter
SIGMA_THESIS = "00000000-0000-4000-8000-0000000000a3"  # closed, with journal entries and a post-mortem
ECHO_DOC = "00000000-0000-4000-8000-0000000000d1"
ECHO_FACT = "00000000-0000-4000-8000-0000000000f1"
ECHO_DOC2 = "00000000-0000-4000-8000-0000000000d2"  # published after the card's week: new in its review
ECHO_FACT2 = "00000000-0000-4000-8000-0000000000f2"
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
    (LUMEN, "us", "Lumen Water Co.", "0000999106", "LMNW", None, None, "Utilities", "Water Utilities", "1231", False),
    (TARA, "in", "Tara Pumps Ltd", None, None, "TARAPUMP", "INE999T01015", "Industrials", "Pumps", "0331", False),
]  # fmt: skip

SCORES = [  # company, evidence, gap, families, bucket
    (ECHO, 72.5, 61.2, ["fundamentals", "text"], "candidate"),
    (KAPPA, 64.0, None, ["fundamentals", "text"], "candidate"),
    (DELTA, 58.0, 30.0, ["fundamentals", "behavior"], "early"),
    (OMEGA, 66.0, 12.0, ["fundamentals", "structural"], "priced_in"),
    (SIGMA, 40.0, None, ["fundamentals"], "excluded"),
    (LUMEN, 50.0, 74.0, ["fundamentals"], "watch"),
    (TARA, 50.0, 68.5, ["fundamentals"], "watch"),
]

CARD_MD = """# Echo Grid Corp. (ECHO) — 2026-W38

Grid equipment demand from data-center interconnects is showing up in backlog before it shows up in revenue.

## Facts
- Total backlog reached $13.2 billion at quarter end [f:00000000-0000-4000-8000-0000000000f1].
- Revenue was $1.16 billion in the quarter ended March 31, 2026 [m:revenue:2026-03-31].

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


OMEGA_MD = """# Omega Systems Inc. (OMGA) — 2026-W31

Server orders from two hyperscalers point to a second year of growth.

## Kill criteria
| Metric | Condition | Check after | Why |
|---|---|---|---|
| `m:evidence` | < 80 | 2026-09-01 | The order-book case needs an Evidence score of at least 80 |
"""

SIGMA_MD = """# Sigma Holdings Inc. (SGMA) — 2026-W14

The holding company trades at a wide discount to the value of its listed stakes and buys back stock.
"""


def quarters() -> list[tuple[date, float]]:
    ends = [date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30),
            date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)]  # fmt: skip
    return [(d, 800e6 + 60e6 * i) for i, d in enumerate(ends)]


FUNDAMENTALS = (
    "revenue",
    "op_income",
    "net_income",
    "pretax_income",
    "tax_expense",
    "cfo",
    "capex",
    "da",
    "total_assets",
    "cash",
    "total_debt",
    "equity",
    "rpo",
    "diluted_shares",
    "shares_outstanding",
)


def echo_rows() -> list[tuple[date, dict[str, float]]]:
    out = []
    for end, revenue in quarters():
        values = (revenue, revenue * 0.2, revenue * 0.15, revenue * 0.19, revenue * 0.04, revenue * 0.22,
                  revenue * 0.05, revenue * 0.03, 9e9, 1.1e9, 2.0e9, 4.5e9, 10e9 + (end.year - 2024) * 1.6e9, 120e6,
                  119e6)  # fmt: skip
        out.append((end, dict(zip(FUNDAMENTALS, values, strict=True))))
    return out


def echo_series() -> list[dict[str, Any]]:
    s2 = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "signals.yaml").read_text(encoding="utf-8"))
    rows = [Quarter(end, {k: Decimal(str(v)) for k, v in row.items()}) for end, row in echo_rows()]
    return series_points(Series(rows, "us"), s2["s2_incremental_roic"])


def seed(conn: psycopg.Connection[Any]) -> None:
    x = conn.execute
    for c in COMPANIES:
        x("insert into companies (id, market, name, cik, ticker, nse_symbol, isin, sector, industry, fiscal_year_end, "
          "in_universe, capex_desk) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s)", c)  # fmt: skip
    for end, row in echo_rows():
        x("insert into fundamentals_q (company_id, period_end, fiscal_label, filed_at, revenue, op_income, net_income, "
          "pretax_income, tax_expense, cfo, capex, da, total_assets, cash, total_debt, equity, rpo, diluted_shares, "
          "shares_outstanding, currency, source) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
          "%s, %s, %s, %s, 'USD', 'sec_xbrl')",
          (ECHO, end, f"Q{(end.month - 1) // 3 + 1} {end.year}", end + timedelta(days=36),
           *(row[c] for c in FUNDAMENTALS)))  # fmt: skip
    # the Company page's charts: what the weekly run writes (pipeline/signals/weekly.py series_points)
    x("insert into company_series (company_id, week_end, points) values (%s, %s, %s)",
      (ECHO, W, json.dumps(echo_series())))  # fmt: skip
    for cid, ev, gap, fam, bucket in SCORES:
        x("insert into scores (company_id, week_end, evidence, gap, families, bucket, weights_version) values "
          "(%s, %s, %s, %s, %s, %s, 'v1')", (cid, W, ev, gap, fam, bucket))  # fmt: skip
        x("insert into company_metrics (company_id, week_end, metrics) values (%s, %s, %s)",
          (cid, W, json.dumps({"revenue_yoy": 0.276 if cid == ECHO else 0.08, "roic": 0.18, "opm": 0.2})))  # fmt: skip
    for cid, sid, strength in [(ECHO, "S1", 0.82), (ECHO, "S9", 0.4), (KAPPA, "S9", 0.4), (DELTA, "S3", 0.6),
                               (LUMEN, "S4", 1.0), (LUMEN, "S5", 0.9), (TARA, "S3", 1.0)]:  # fmt: skip
        x("insert into signal_values (company_id, week_end, signal_id, fired, strength, inputs) values "
          "(%s, %s, %s, true, %s, '{}')", (cid, W, sid, strength))  # fmt: skip
        x("insert into signal_values (company_id, week_end, signal_id, fired, strength, inputs) values "
          "(%s, %s, %s, true, %s, '{}')", (cid, W - timedelta(days=7), sid, strength))  # fmt: skip
    # §1.5: R3 (an auditor change) is hard, so SIGMA is excluded; R4 (share count +10% YoY) is soft
    x("insert into redflag_values (company_id, week_end, flag_id, hard, inputs) values "
      "(%s, %s, 'R3', true, '{\"status\": \"fired\"}'), (%s, %s, 'R4', false, '{\"status\": \"fired\"}')",
      (SIGMA, W, OMEGA, W))  # fmt: skip
    # R1 (soft) fired for ECHO two and one week before and is clear in the scored week (no row): its review shows no
    # red flag starting (M7 review R2-F1)
    for weeks in (2, 1):
        x("insert into redflag_values (company_id, week_end, flag_id, hard, inputs) values "
          "(%s, %s, 'R1', false, '{\"status\": \"fired\"}')", (ECHO, W - timedelta(days=7 * weeks)))  # fmt: skip
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
    # a fact about the June quarter published after the card's week: not in its pack, new in its review (M7 review
    # R2-F2)
    quote2 = "Backlog was $14.0 billion at June 30, 2026."
    x("insert into documents (id, company_id, kind, url, title, published_at, sha256, raw_path, status) values "
      "(%s, %s, 'presentation', 'https://www.sec.gov/Archives/edgar/data/999101/echo-investor-day.htm', "
      "'Echo Grid investor day', '2026-09-21 12:00+00', %s, 'e2e/echo-investor-day.htm', 'extracted')",
      (ECHO_DOC2, ECHO, "1" * 64))  # fmt: skip
    x("insert into facts (id, company_id, document_id, fact_type, subject, subject_key, value_num, unit, currency, "
      "scale_word, period_end, as_of, quote, char_start, char_end, extraction_model, confidence, verification_status) "
      "values (%s, %s, %s, 'backlog', 'backlog', 'backlog:total', 14000000000, 'usd', 'USD', 'billion', '2026-06-30', "
      "'2026-06-30', %s, 0, %s, 'e2e', 0.90, 'verified')",
      (ECHO_FACT2, ECHO, ECHO_DOC2, quote2, len(quote2)))  # fmt: skip
    x("insert into entities (id, name, normalized, kind) values (%s, 'Nimbus Compute Corp.', 'nimbus compute', "
      "'company')", (NIMBUS,))  # fmt: skip
    x("insert into links (from_company_id, to_entity_id, relation, fact_id) values (%s, %s, 'customer', %s)",
      (ECHO, NIMBUS, ECHO_FACT))  # fmt: skip

    pack = {"version": 1, "week": "2026-W38", "week_end": str(W),
            "metrics": [{"id": "m:revenue:2026-03-31", "name": "revenue", "period_end": "2026-03-31",
                         "value": "1160000000", "unit": "usd", "source": "sec_xbrl"}],
            "signals": [{"id": "s:S1", "kind": "signal", "fired": True, "strength": "0.82", "inputs": {}},
                        {"id": "s:S9", "kind": "signal", "fired": True, "strength": "0.4", "inputs": {}}],
            "context": [{"id": "c:C2", "value": "0.12", "pct": None, "inputs": c2},
                        {"id": "c:evidence", "value": "72.5", "pct": None, "inputs": {}}],
            "facts": [{"id": f"f:{ECHO_FACT}", "fact_type": "backlog", "subject": "backlog", "value": "13200000000",
                       "unit": "usd", "currency": "USD", "as_of": "2026-08-05", "quote": quote}],
            "kill_metrics": [{"id": "m:revenue_ttm_yoy", "description": "TTM revenue vs the TTM a year earlier",
                              "value": "0.24", "unit": "ratio"}],
            # the window after the pack's quarter (2026-03-31): what accept() writes as next_review, so the verdict's
            # window (after 2026-06-30) differs from it (M7 review R2-F4)
            "next_filing": {"period_end": "2026-06-30", "form": "10-Q", "opens": "2026-07-01",
                            "closes": "2026-08-14"}}  # fmt: skip
    card = {"summary": "Grid equipment demand shows up in backlog first.",
            "facts": [{"text": quote, "cites": [f"f:{ECHO_FACT}"]}]}  # fmt: skip
    x("insert into theses (id, company_id, state, card_md, card_json, evidence_pack, author, validation, "
      "created_week) values (%s, %s, 'research', %s, %s, %s, 'routine', '{\"ok\": true}', %s)",
      (ECHO_THESIS, ECHO, CARD_MD, json.dumps(card), json.dumps(pack), W))  # fmt: skip
    x("insert into kill_criteria (thesis_id, metric, operator, threshold, check_after, status, last_value, "
      "last_checked, why) values (%s, 'm:revenue_ttm_yoy', '<', 0.05, '2026-11-20', 'ok', 0.24, %s, "
      "'Growth thesis fails if TTM revenue growth drops below 5%%')", (ECHO_THESIS, W))  # fmt: skip

    # a kill criterion (on the Evidence score) moved this thesis to Review without a new quarter (M7 review R1-F1)
    omega_pack = {"version": 1, "week": "2026-W31", "week_end": "2026-07-31", "metrics": [], "signals": [],
                  "context": [{"id": "c:evidence", "value": "82.0", "pct": None, "inputs": {}}],
                  "kill_metrics": [{"id": "m:evidence", "description": "Evidence score, latest scored week (0-100)",
                                    "value": "82.0", "unit": "score"}]}  # fmt: skip
    x(
        "insert into theses (id, company_id, state, card_md, card_json, evidence_pack, author, validation, "
        "created_week, accepted_at, next_review) values (%s, %s, 'review', %s, '{}', %s, 'routine', '{\"ok\": true}', "
        "'2026-07-31', '2026-08-03 09:00+00', '2026-11-14')",
        (OMEGA_THESIS, OMEGA, OMEGA_MD, json.dumps(omega_pack)),
    )
    x("insert into kill_criteria (thesis_id, metric, operator, threshold, check_after, status, last_value, "
      "last_checked, triggered_week, why) values (%s, 'm:evidence', '<', 80, '2026-09-01', 'triggered', 66, %s, %s, "
      "'The order-book case needs an Evidence score of at least 80')", (OMEGA_THESIS, W, W))  # fmt: skip

    # a closed thesis with its journal and post-mortem (the screens' other states, for the axe run)
    x("insert into theses (id, company_id, state, card_md, card_json, evidence_pack, author, validation, "
      "created_week, accepted_at) values (%s, %s, 'closed', %s, '{}', '{}', 'routine', '{\"ok\": true}', "
      "'2026-04-03', '2026-04-10 09:00+00')", (SIGMA_THESIS, SIGMA, SIGMA_MD))  # fmt: skip
    x("insert into journal (thesis_id, entry_date, action, portfolio_pct, reason) values "
      "(%s, '2026-05-15', 'start_position', 2.0, 'The discount to book is wide and the company buys back stock.'), "
      "(%s, '2026-08-20', 'exit', null, 'The discount closed.')", (SIGMA_THESIS, SIGMA_THESIS))  # fmt: skip
    x("insert into postmortems (thesis_id, what_happened, thesis_right, signals_right, lessons) values "
      "(%s, 'The discount to book closed within a quarter.', true, '{\"note\": \"S7 fired twice before it did.\"}', "
      "'Size the position before the second buyback.')", (SIGMA_THESIS,))  # fmt: skip

    # ownership, an insider buy filed after the card's week (new in its review) and an index change
    x("insert into ownership_q (company_id, quarter_end, filed_at, inst_holders, inst_pct, source) values "
      "(%s, '2026-03-31', '2026-05-15 12:00+00', 398, 0.69, 'sec_13f'), "
      "(%s, '2026-06-30', '2026-08-14 12:00+00', 412, 0.71, 'sec_13f')", (ECHO, ECHO))  # fmt: skip
    x("insert into insider_events (company_id, event_date, filed_at, person, role, kind, shares, value, currency, "
      "source_url) values (%s, '2026-09-17', '2026-09-21 12:00+00', 'A. Director', 'Director', 'open_market_buy', "
      "5000, 510000, 'USD', 'https://www.sec.gov/Archives/edgar/data/999101/form4.xml')", (ECHO,))  # fmt: skip
    x("insert into corp_events (company_id, event_date, filed_at, kind, detail, source_url) values "
      "(%s, '2026-07-01', '2026-07-02 12:00+00', 'index_change', '{\"index\": \"S&P MidCap 400\"}', "
      "'https://www.sec.gov/Archives/edgar/data/999101/idx-8k.htm')", (ECHO,))  # fmt: skip

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

    # the digest as pipeline/digest/weekly.py writes it (overhaul PR 5; tests/digest/test_weekly_body.py): Home shows
    # This week and What changed, and turns the APP_URL in its company links into paths on its own host
    app = "https://doomberg.example"
    digest = (
        "Week ending 2026-09-18. Research only: no orders, no price alerts.\n\n"
        "## This week\n\n"
        "US 4 → stage 4 → candidates 1 → new 0 · 1 of 4 fire one family, capped at 55\n\n"
        "IN 1 → stage 1 → candidates 1 → new 0 · 0 of 1 fire one family, capped at 55\n\n"
        "## To do\n\n"
        "- Cards to accept or dismiss: 1 (Echo Grid Corp. (ECHO))\n"
        "- Theses in review: 1 (Omega Systems Inc. (OMGA))\n\n"
        "## What changed\n\n"
        f"- [ECHO]({app}/company/{ECHO}) entered Candidate: Evidence 72.5\n"
        f"- [KAPPA]({app}/company/{KAPPA}) entered Candidate: Evidence 64\n"
        f"- [OMGA]({app}/company/{OMEGA}) entered Priced-in: Evidence 66\n"
        f"- [DLTP]({app}/company/{DELTA}) entered Early: Evidence 58\n\n"
        "## Health\n\n"
        "**Stale data:** twelvedata (stale). Signals and scores that read these sources may be out of date.\n\n"
        "Actions: 812 of 2,000 this cycle, projected 1,340.\n"
    )
    x("insert into digests (week_end, title, body_md) values (%s, 'Doomberg weekly — 2026-W38', %s)", (W, digest))
    x("insert into source_health (source, last_success, last_error, stale) values "
      "('sec', '2026-09-18 06:00+00', null, false), ('nse', '2026-09-18 06:00+00', null, false), "
      "('bse', '2026-08-01 06:00+00', null, false), "
      "('twelvedata', null, 'stale: 13 downloads failed', true)")  # fmt: skip
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

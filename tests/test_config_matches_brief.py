"""M0-06: every default in BRIEF §4.6-4.8 (plus §1.5, §1.7, §4.4, §4.7, §4.10.5, §4.11) equals the config value.

Values below are transcribed by hand from docs/BRIEF.md, with the section each comes from. If a config value
changes, this test fails until the brief (a protected path) is changed too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"

EXPECTED: list[tuple[str, str, Any, str]] = [
    # file, dotted key, brief value, brief ref
    ("signals.yaml", "shared.tax_rate_clip", [0.10, 0.35], "§4.6 tax rate"),
    ("signals.yaml", "shared.tax_rate_default.us", 0.21, "§4.6 tax rate"),
    ("signals.yaml", "shared.tax_rate_default.in", 0.25, "§4.6 tax rate"),
    ("signals.yaml", "shared.ic_floor_pct_assets", 0.05, "§4.6 invested capital"),
    ("signals.yaml", "shared.roic_ic_mean_quarters", 4, "§4.6 ROIC"),
    ("signals.yaml", "s1_orderbook.min_growth_gap", 0.10, "§4.6 S1"),
    ("signals.yaml", "s1_orderbook.consecutive_quarters", 2, "§4.6 S1"),
    ("signals.yaml", "s1_orderbook.coverage_must_rise_yoy", True, "§4.6 S1"),
    ("signals.yaml", "s1_orderbook.strength_divisor", 0.30, "§4.6 S1"),
    ("signals.yaml", "s1_orderbook.min_coverage", 0.25, "§4.6 S1 (SPEC_ISSUES 42)"),
    ("signals.yaml", "s2_incremental_roic.lookback_quarters", 12, "§4.6 S2"),
    ("signals.yaml", "s2_incremental_roic.min_delta_ic_pct", 0.05, "§4.6 S2"),
    ("signals.yaml", "s2_incremental_roic.min_inc_roic", 0.15, "§4.6 S2"),
    ("signals.yaml", "s2_incremental_roic.roic_band", [0.03, 0.12], "§4.6 S2"),
    ("signals.yaml", "s2_incremental_roic.roic_rise_min", 0.03, "§4.6 S2"),
    ("signals.yaml", "s2_incremental_roic.roic_rise_lookback_quarters", 8, "§4.6 S2"),
    ("signals.yaml", "s2_incremental_roic.strength_base", 0.5, "§4.6 S2"),
    ("signals.yaml", "s2_incremental_roic.strength_scale", 0.5, "§4.6 S2"),
    ("signals.yaml", "s2_incremental_roic.strength_divisor", 0.25, "§4.6 S2"),
    ("signals.yaml", "s3_operating_leverage.growth_rising_quarters", 2, "§4.6 S3"),
    ("signals.yaml", "s3_operating_leverage.min_opm_rise", 0.01, "§4.6 S3"),
    ("signals.yaml", "s3_operating_leverage.opm_lookback_quarters", 4, "§4.6 S3"),
    ("signals.yaml", "s3_operating_leverage.strength_divisor", 0.05, "§4.6 S3"),
    ("signals.yaml", "s4_earnings_quality.min_ccr", 1.0, "§4.6 S4"),
    ("signals.yaml", "s4_earnings_quality.min_ccr_rise_yoy", 0.2, "§4.6 S4"),
    ("signals.yaml", "s4_earnings_quality.max_sloan", 0.05, "§4.6 S4"),
    ("signals.yaml", "s4_earnings_quality.strength_divisor", 0.5, "§4.6 S4"),
    ("signals.yaml", "s4_earnings_quality.cfo_must_rise_yoy", True, "§4.6 S4 (SPEC_ISSUES 41)"),
    ("signals.yaml", "s4_earnings_quality.ni_min_ratio_yoy", 0.9, "§4.6 S4 (SPEC_ISSUES 47)"),
    ("signals.yaml", "s4_earnings_quality.exclude_sic", [[6000, 6411]], "§4.6 S4 (SPEC_ISSUES 47)"),
    ("signals.yaml", "s5_capital_discipline.a_max_share_change", -0.02, "§4.6 S5"),
    ("signals.yaml", "s5_capital_discipline.a_max_nd_rise", 0.10, "§4.6 S5"),
    ("signals.yaml", "s5_capital_discipline.a_strength_divisor", 0.06, "§4.6 S5"),
    ("signals.yaml", "s5_capital_discipline.b_min_prior_dilution", 0.05, "§4.6 S5"),
    ("signals.yaml", "s5_capital_discipline.b_prior_years", 2, "§4.6 S5"),
    ("signals.yaml", "s5_capital_discipline.b_max_latest_change", 0.0, "§4.6 S5"),
    ("signals.yaml", "s5_capital_discipline.b_strength", 0.6, "§4.6 S5"),
    ("signals.yaml", "s6_derisking.window_quarters", [8, 4], "§4.6 S6"),
    ("signals.yaml", "s6_derisking.min_past_leverage", 3.0, "§4.6 S6"),
    ("signals.yaml", "s6_derisking.max_current_leverage", 1.5, "§4.6 S6"),
    ("signals.yaml", "s6_derisking.min_interest_coverage", 5.0, "§4.6 S6"),
    ("signals.yaml", "s6_derisking.strength", 0.8, "§4.6 S6"),
    ("signals.yaml", "s7_insider.us_min_insiders", 2, "§4.6 S7"),
    ("signals.yaml", "s7_insider.us_min_buy_usd", 25_000, "§4.6 S7"),
    ("signals.yaml", "s7_insider.us_window_days", 60, "§4.6 S7"),
    ("signals.yaml", "s7_insider.us_min_total_usd", 250_000, "§4.6 S7"),
    ("signals.yaml", "s7_insider.us_ignore_roles", ["10% owner"], "§4.6 S7 (SPEC_ISSUES 49)"),
    ("signals.yaml", "s7_insider.in_min_promoter_buy_inr", 20_000_000, "§4.6 S7 (Rs 2 crore)"),
    ("signals.yaml", "s7_insider.in_window_days", 90, "§4.6 S7"),
    ("signals.yaml", "s7_insider.in_pledge_drop_pp", 5.0, "§4.6 S7"),
    ("signals.yaml", "s7_insider.in_pledge_strength", 0.6, "§4.6 S7"),
    ("signals.yaml", "s7_insider.strength_base", 0.5, "§4.6 S7"),
    ("signals.yaml", "s7_insider.strength_per_extra_insider", 0.1, "§4.6 S7"),
    ("signals.yaml", "s7_insider.strength_log2_scale", 0.1, "§4.6 S7"),
    ("signals.yaml", "s8_discovery.us_max_holder_pct_in_size_decile", 40, "§4.6 S8"),
    ("signals.yaml", "s8_discovery.us_min_holder_growth_qoq", 0.15, "§4.6 S8"),
    ("signals.yaml", "s8_discovery.us_consecutive_quarters", 2, "§4.6 S8"),
    ("signals.yaml", "s8_discovery.us_strength_divisor", 0.5, "§4.6 S8"),
    ("signals.yaml", "s8_discovery.in_max_fii_dii_pct", 15.0, "§4.6 S8"),
    ("signals.yaml", "s8_discovery.in_min_rise_pp", 2.0, "§4.6 S8"),
    ("signals.yaml", "s8_discovery.in_rise_quarters", 2, "§4.6 S8"),
    ("signals.yaml", "s8_discovery.in_strength_divisor_pp", 6.0, "§4.6 S8"),
    ("signals.yaml", "s9_text.lookback_quarters", 2, "§4.6 S9"),
    (
        "signals.yaml",
        "s9_text.fact_types",
        [
            "order_win",
            "customer_win",
            "capacity_addition",
            "price_increase",
            "lead_time",
            "new_segment",
            "governance_flag",
        ],
        "§4.6 S9",
    ),
    ("signals.yaml", "s9_text.strength_per_fact", 0.4, "§4.6 S9"),
    ("signals.yaml", "s10_special.spinoff_demerger_months", 18, "§4.6 S10"),
    ("signals.yaml", "s10_special.reorganization_months", 24, "§4.6 S10"),
    ("signals.yaml", "s10_special.rights_issue_months", 6, "§4.6 S10"),
    ("signals.yaml", "s10_special.strength", 0.6, "§4.6 S10"),
    ("signals.yaml", "s11_capex.min_lag_pp", 10.0, "§4.11 S11"),
    ("signals.yaml", "s11_capex.second_order_distance", 2, "§4.11 S11"),
    ("signals.yaml", "s11_capex.strength_base", 0.5, "§4.11 S11"),
    ("signals.yaml", "s11_capex.strength_india_export_bonus", 0.25, "§4.11 S11"),
    ("signals.yaml", "s11_capex.strength_s1_bonus", 0.25, "§4.11 S11"),
    ("signals.yaml", "s12_cycle.max_capex_to_da", 1.0, "§4.6 S12"),
    ("signals.yaml", "s12_cycle.underinvest_years", 3, "§4.6 S12"),
    ("signals.yaml", "s12_cycle.demand_turn_quarters", 2, "§4.6 S12"),
    ("signals.yaml", "s12_cycle.min_tightness_facts", 2, "§4.6 S12"),
    ("signals.yaml", "s12_cycle.tightness_lookback_quarters", 2, "§4.6 S12"),
    ("signals.yaml", "s12_cycle.requires_any_of", ["S2", "S6"], "§4.6 S12"),
    ("signals.yaml", "s12_cycle.strength", 0.6, "§4.6 S12"),
    # §4.8 scores and buckets, §1.7
    (
        "signals.yaml",
        "scores.families",
        {
            "fundamentals": ["S1", "S2", "S3", "S4", "S5", "S6"],
            "behavior": ["S7", "S8"],
            "text": ["S9"],
            "structural": ["S10"],
            "capex": ["S11"],
            "cycle": ["S12"],
        },
        "§4.8.1",
    ),
    ("signals.yaml", "scores.max_signals_per_family", 2, "§4.8.2"),
    ("signals.yaml", "scores.evidence_divisor", 2.0, "§4.8.3"),
    ("signals.yaml", "scores.single_family_cap", 55, "§4.8.3"),
    ("signals.yaml", "scores.min_families", 2, "§1.7 / §4.8.3"),
    ("signals.yaml", "scores.soft_flag_penalty", 10, "§4.8.3"),
    ("signals.yaml", "scores.gap_min_metrics", 2, "§4.8.4"),
    ("signals.yaml", "scores.buckets.candidate", {"min_evidence": 60, "min_gap": 50}, "§1.7"),
    ("signals.yaml", "scores.buckets.priced_in", {"min_evidence": 60, "max_gap_exclusive": 50}, "§1.7"),
    (
        "signals.yaml",
        "scores.buckets.early",
        {"min_evidence": 40, "max_evidence": 59, "min_families": 2, "min_gap": 50},
        "§1.7",
    ),
    ("signals.yaml", "scores.weekly_new_candidates", 10, "§1.7 / §4.8.6"),
    ("signals.yaml", "scores.novelty_weeks", 12, "§1.7 / §4.8.6"),
    ("signals.yaml", "scores.us_price_candidate_min_evidence", 40, "§4.4"),
    (
        "signals.yaml",
        "xbrl_map.revenue",
        ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "§4.1.2",
    ),
    ("signals.yaml", "xbrl_map.op_income", ["OperatingIncomeLoss"], "§4.1.2"),
    ("signals.yaml", "xbrl_map.cfo", ["NetCashProvidedByUsedInOperatingActivities"], "§4.1.2"),
    ("signals.yaml", "xbrl_map.capex", ["PaymentsToAcquirePropertyPlantAndEquipment"], "§4.1.2"),
    ("signals.yaml", "xbrl_map.da", ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"], "§4.1.2"),
    ("signals.yaml", "xbrl_map.rpo", ["RevenueRemainingPerformanceObligation"], "§4.1.2"),
    ("signals.yaml", "xbrl_map.diluted_shares", ["WeightedAverageNumberOfDilutedSharesOutstanding"], "§4.1.2"),
    ("signals.yaml", "xbrl_map.shares_outstanding", ["dei:EntityCommonStockSharesOutstanding"], "§4.1.2"),
    # §4.8 weights (initially equal) and §4.10.5 lab rules
    (
        "weights.yaml",
        "families",
        {"fundamentals": 1.0, "behavior": 1.0, "text": 1.0, "structural": 1.0, "capex": 1.0, "cycle": 1.0},
        "§4.8.3",
    ),
    ("weights.yaml", "signals", {f"S{i}": 1.0 for i in range(1, 13)}, "§1.7 equal weights"),
    # C4's weight stays in weights.yaml until a weights PR drops it; gap() never reads it (SPEC_ISSUES 48)
    ("weights.yaml", "context.C1", 1.0, "§1.7 Gap equal weights"),
    ("weights.yaml", "context.C2", 1.0, "§1.7 Gap equal weights"),
    ("weights.yaml", "context.C3", 1.0, "§1.7 Gap equal weights"),
    ("weights.yaml", "lab_rules.promote_weight", 1.5, "§4.10.5"),
    ("weights.yaml", "lab_rules.promote_min_t_nw", 2.0, "§4.10.5"),
    ("weights.yaml", "lab_rules.neutral_weight", 1.0, "§4.10.5"),
    ("weights.yaml", "lab_rules.demote_weight", 0.0, "§4.10.5"),
    ("weights.yaml", "lab_rules.demote_max_t_nw", -2.0, "§4.10.5"),
    # §4.10 Signal Lab defaults (M8 review ideas: a period or horizon change shows here)
    ("lab.yaml", "horizons_months", [12, 24, 36], "§4.10.1"),
    ("lab.yaml", "periods.in_sample", ["2012-01", "2018-12"], "§4.10.3"),
    ("lab.yaml", "periods.out_of_sample", ["2019-01", "2025-12"], "§4.10.3"),
    ("lab.yaml", "event_window_months", 12, "§4.10.2"),
    ("lab.yaml", "deciles", 10, "§4.10.3"),
    ("lab.yaml", "india_min_quarters", 8, "§4.10.7"),
    # §4.7 context metrics
    ("context.yaml", "c1.history_years", 10, "§4.7 C1"),
    ("context.yaml", "c2_reverse_dcf.years", 10, "§4.7 C2"),
    ("context.yaml", "c2_reverse_dcf.discount_rate", {"us": 0.09, "in": 0.12}, "§4.7 C2"),
    ("context.yaml", "c2_reverse_dcf.terminal_growth", {"us": 0.025, "in": 0.045}, "§4.7 C2"),
    ("context.yaml", "c2_reverse_dcf.margin_floor", 0.02, "§4.7 C2"),
    ("context.yaml", "c2_reverse_dcf.margin_median_years", 5, "§4.7 C2"),
    ("context.yaml", "c2_reverse_dcf.s2c_median_years", 5, "§4.7 C2"),
    ("context.yaml", "c2_reverse_dcf.s2c_clip", [0.5, 4.0], "§4.7 C2"),
    ("context.yaml", "c2_reverse_dcf.s2c_default", 1.5, "§4.7 C2"),
    ("context.yaml", "c2_reverse_dcf.brentq_bounds", [-0.20, 0.60], "§4.7 C2"),
    (
        "context.yaml",
        "c2_reverse_dcf.evidence_growth",
        {
            "w_orderbook": 0.4,
            "w_cagr3": 0.3,
            "w_latest_yoy": 0.3,
            "orderbook_clip": [-0.2, 0.6],
            "cap": [-0.10, 0.40],
            "latest_yoy_basis": "ttm",
            "orderbook_min_coverage": 0.25,
        },
        "§4.7 C2",
    ),
    ("context.yaml", "c2_reverse_dcf.growth_must_add_value", True, "§4.7 C2 (SPEC_ISSUES 43)"),
    ("context.yaml", "c2_reverse_dcf.score_center", 50, "§4.7 C2"),
    ("context.yaml", "c2_reverse_dcf.score_slope", 250, "§4.7 C2"),
    ("context.yaml", "c3_runup.lookback_weeks", 52, "§4.7 C3"),
    ("context.yaml", "c3_runup.already_ran_pct", 90, "§4.7 C3 / §1.6"),
    ("context.yaml", "c3_runup.min_population", 30, "§4.7 C3 (SPEC_ISSUES 48)"),
    # §1.5 red flags
    ("redflags.yaml", "R1", {"type": "soft", "sloan_min": 0.10, "cfo_ni_max": 0.5}, "§1.5 R1"),
    (
        "redflags.yaml",
        "R2",
        {"type": "soft", "receivables_minus_revenue_growth_pp": 20.0, "revenue_basis": "quarter"},
        "§1.5 R2 (SPEC_ISSUES 47)",
    ),
    ("redflags.yaml", "R3.type", "hard", "§1.5 R3"),
    ("redflags.yaml", "R3.auditor_change_months", 12, "§1.5 R3"),
    ("redflags.yaml", "R4", {"type": "soft", "share_growth_min": 0.10, "unless_acquisition": True}, "§1.5 R4"),
    ("redflags.yaml", "R5.pledge", {"type": "hard", "min_pledged_pct_of_promoter": 20.0}, "§1.5 R5"),
    ("redflags.yaml", "R5.surveillance.type", "hard", "§1.5 R5"),
    ("redflags.yaml", "R5.related_party", {"type": "soft", "min_rpt_revenue_pct": 10.0}, "§1.5 R5"),
    ("redflags.yaml", "R6", {"type": "soft", "consecutive_quarters": 4, "unless_signal": "S1"}, "§1.5 R6"),
    # §4.9 hype words
    ("terms.yaml", "hype", ["multibagger", "can't lose", "guaranteed", "sure shot", "rocket", "to the moon"], "§4.9"),
    ("terms.yaml", "prefilter.min_score", 3, "Appendix F.4.2"),
    # §1.3 universes
    ("universe_us.yaml", "min_ttm_revenue_usd", 50_000_000, "§1.3"),
    ("universe_us.yaml", "candidate_min_mcap_usd", 300_000_000, "§1.3"),
    ("universe_us.yaml", "exclude.sic", ["6770"], "§1.3 SPACs"),
    ("universe_in.yaml", "series", ["EQ"], "§1.3"),
    ("universe_in.yaml", "candidate_min_mcap_inr", 5_000_000_000, "§1.3 (Rs 500 crore)"),
    ("categories.yaml", "direction", {"rising_min_sigma": 0.5, "falling_max_sigma": -0.5}, "§4.11"),
]


def _get(doc: dict[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        assert isinstance(cur, dict) and part in cur, f"missing key {dotted}"
        cur = cur[part]
    return cur


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.mark.parametrize(("file", "key", "expected", "ref"), EXPECTED, ids=[f"{f}:{k}" for f, k, _, _ in EXPECTED])
def test_default_matches_brief(file: str, key: str, expected: Any, ref: str) -> None:
    assert _get(_load(file), key) == expected, f"{file}:{key} differs from BRIEF {ref}"


def test_categories_match_brief() -> None:
    assert sorted(_load("categories.yaml")["categories"]) == sorted(
        [
            "compute",
            "networking",
            "optical",
            "power_equipment",
            "grid",
            "cooling",
            "construction",
            "on_site_power",
            "electronics_manufacturing",
        ]
    ), "BRIEF §1.10 category map"


def test_capex_seed_matches_appendix_h() -> None:
    seed = _load("capex_seed.yaml")
    us = [t for g in seed["us"].values() for t in g]
    assert us == [
        "MSFT",
        "GOOGL",
        "AMZN",
        "META",
        "ORCL",
        "CRWV",
        "NVDA",
        "AMD",
        "AVGO",
        "MRVL",
        "MU",
        "INTC",
        "ANET",
        "DELL",
        "SMCI",
        "HPE",
        "JBL",
        "FLEX",
        "GLW",
        "COHR",
        "LITE",
        "CIEN",
        "APH",
        "WDC",
        "STX",
        "AMAT",
        "LRCX",
        "KLAC",
        "GEV",
        "ETN",
        "VRT",
        "HUBB",
        "POWL",
        "NVT",
        "CMI",
        "CAT",
        "MOD",
        "TT",
        "JCI",
        "BE",
        "FLNC",
        "PWR",
        "EME",
        "FIX",
        "MTZ",
        "PRIM",
        "STRL",
        "EQIX",
        "DLR",
        "IRM",
        "CEG",
        "VST",
        "TLN",
        "NRG",
        "D",
        "SO",
        "AEP",
        "ETR",
        "XEL",
        "NEE",
        "DUK",
    ]
    assert len(seed["india"]) == 41
    assert len({e["nse"] for e in seed["india"]}) == 41, "duplicate proposed NSE symbols"


def test_guards_yaml_is_appendix_e_verbatim() -> None:
    brief = (CONFIG.parent / "docs" / "BRIEF.md").read_text(encoding="utf-8")
    start = brief.index("```yaml", brief.index("## Appendix E")) + len("```yaml\n")
    block = brief[start : brief.index("\n```", start) + 1]
    body = (CONFIG / "guards.yaml").read_text(encoding="utf-8").split("\n", 1)[1]
    assert body == block


# ---------------------------------------------------------------- every protected key is read (M4 review R1-F9)

PIPELINE = CONFIG.parent / "pipeline"
READ_BY_CODE = ("signals.yaml", "redflags.yaml", "context.yaml")
DATA_MAPS = {"xbrl_map", "ind_as_map", "families", "benchmarks"}  # their keys are data, iterated rather than named
DATA_KEYS = {"version", "us", "in"}  # market codes are read as cfg[market]


def _keys(doc: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(doc, dict):
        for k, v in doc.items():
            dotted = f"{path}.{k}" if path else str(k)
            if str(k) in DATA_KEYS:
                continue
            out.append(dotted)
            if str(k) not in DATA_MAPS:
                out += _keys(v, dotted)
    return out


def _is_read(key: str, source: str) -> bool:
    """The key is named in a subscript (cfg["key"]), a .get("key", ...), a section lookup (ctx.section("key")) or a
    helper call (_dec(c, "key"))."""
    import re

    q = re.escape(key)
    pattern = rf"""\[\s*["']{q}["']\s*\]|\.(?:get|section)\(\s*["']{q}["']|,\s*["']{q}["']\s*\)"""
    return re.search(pattern, source) is not None


def test_every_protected_key_is_read_by_code() -> None:
    """A protected threshold that no code reads is a silent restatement: changing it (through a human-approved PR)
    would change nothing. R1..R6 and S-ids are read as cfg[flag_id]/cfg[section] too, so only leaf names are checked
    for them."""
    source = "\n".join(p.read_text(encoding="utf-8") for p in PIPELINE.rglob("*.py"))
    missing = []
    for name in READ_BY_CODE:
        for dotted in _keys(_load(name)):
            leaf = dotted.rsplit(".", 1)[-1]
            if not _is_read(leaf, source):
                missing.append(f"{name}:{dotted}")
    assert not missing, f"config keys no code reads: {missing}"

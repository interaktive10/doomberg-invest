"""Text fact types (BRIEF §1.9 and Appendix F.1) and the units a fact can carry (Appendix F.2 `facts.unit`)."""

from __future__ import annotations

FACT_TYPES: dict[str, str] = {
    # Appendix F.1 (carried over from the Capex Ledger brief)
    "capex_guidance": "A company's stated expectation for capital expenditures",
    "capex_reported": "Reported capital expenditures (XBRL PaymentsToAcquirePropertyPlantAndEquipment and text)",
    "backlog": "Stated backlog/orders (industrial, contractors)",
    "rpo": "Remaining performance obligations (XBRL RevenueRemainingPerformanceObligation and text)",
    "lead_time": "A stated lead time for equipment or capacity",
    "capacity_addition": "New or expanded capacity: MW/GW, factories, square feet, sites, with timing",
    "commitment_lease": "Leases not yet commenced, data-center leases, lease commitments",
    "commitment_purchase": "Purchase obligations, capacity/compute purchase commitments, take-or-pay",
    "commitment_ppa": "Power purchase and energy supply agreements (counterparty, MW, term)",
    "financing": "Debt, JV or SPV financing tied to AI/data-center infrastructure",
    "customer_concentration": "Stated share of revenue from the largest customers",
    "supply_link": "A named customer/supplier/partner relationship tied to AI infrastructure",
    "utility_load": "Utility large-load or data-center pipeline (GW, requests, contracts)",
    "risk_factor_change": (
        "Added, removed or modified risk-factor paragraphs on AI, data centers, power or supply chain"
    ),
    # BRIEF §1.9 general types; what each is not: docs/SPEC_ISSUES.md 61 (Verify-1 V1-KIND checks the quote)
    "order_win": (
        "An order, contract, award or booking the company won, with its value, customer or program; not an "
        "acquisition or sale of a business, a settlement, refund or escrow, revenue or guidance"
    ),
    "customer_win": "A new named customer or program the company won",
    "price_increase": "A price increase or pricing action on the company's own products or services; not a margin",
    "new_segment": "A segment or business line the company newly created or entered; not its existing segments",
    "governance_flag": (
        "Auditor change (the independent accounting firm), material weakness, going concern, restatement (added or "
        "removed); not an officer's departure, a debt default or a lawsuit"
    ),
    "export_exposure": "A stated export share or overseas order book (India: US/data-center exports)",
}

UNITS = ("usd", "usd_per_year", "mw", "gw", "mwh", "sq_ft", "months", "weeks", "years", "percent", "count", "other")
SCALE_WORDS = ("thousand", "million", "billion", "trillion")

# F.4.7: the subject_key prefix each type's keys use (config/subject_keys.yaml)
KEY_PREFIX: dict[str, tuple[str, ...]] = {
    "capex_guidance": ("capex_guidance:",),
    "capex_reported": ("capex_reported:",),
    "backlog": ("backlog:",),
    "rpo": ("rpo:",),
    "lead_time": ("lead_time:",),
    "capacity_addition": ("capacity:",),
    "commitment_lease": ("lease_not_commenced:",),
    "commitment_purchase": ("purchase_obligations:",),
    "commitment_ppa": ("ppa:",),
    "financing": ("financing:",),
    "customer_concentration": ("customer_concentration:",),
    "supply_link": ("link:",),
    "utility_load": ("large_load:",),
    "risk_factor_change": ("risk:",),
    "order_win": ("order_win:",),
    "customer_win": ("customer_win:",),
    "price_increase": ("price_increase:",),
    "new_segment": ("new_segment:",),
    "governance_flag": ("governance:",),
    "export_exposure": ("export_exposure:",),
}

# links.relation for a verified fact with a counterparty (Appendix F.2 `links`)
RELATION: dict[str, str] = {
    "commitment_lease": "lessor",
    "commitment_ppa": "ppa_counterparty",
    "financing": "lender",
    "order_win": "customer",
    "customer_win": "customer",
    "customer_concentration": "customer",
    "supply_link": "partner",
    "commitment_purchase": "supplier",
}


def definitions_text() -> str:
    """{{fact_types_with_definitions}} for P-01."""
    return "; ".join(f"{k} ({v})" for k, v in FACT_TYPES.items())

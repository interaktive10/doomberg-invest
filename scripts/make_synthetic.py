#!/usr/bin/env python3
"""F-SYN (BRIEF §9): 12 fictional-company documents with planted facts and a ground truth. Seed 7.

Documents (fixtures/syn/): 4 press releases (EX-99.1 HTML and an India announcement), 4 10-Q-style HTML filings (a
table of contents, an inline-XBRL hidden header, MD&A, notes on revenue/RPO, leases, commitments and debt), 2
versions of a 10-K's risk factors (Item 1A), and 2 investor-presentation PDFs. Every planted fact is one sentence
written once into its document; ground_truth.json lists each with its type, key, value (scaled), unit and the exact
quote. Each document also carries distractors P-01 must not return (share repurchases, dividends, EPS, stock price,
analyst ratings).

The numbers vary with the seed; the sentence templates don't. `python scripts/make_synthetic.py` rewrites the files
(deterministic: same seed, same bytes)."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

SEED = 7
OUT = Path(__file__).resolve().parent.parent / "fixtures" / "syn"

COMPANIES = {
    "NMBS": {"name": "Nimbus Compute Corp.", "fye": "0630", "market": "us"},
    "VOLT": {"name": "Voltara Grid Systems, Inc.", "fye": "1231", "market": "us"},
    "KYST": {"name": "Keystone Power & Light Co.", "fye": "1231", "market": "us"},
    "CLST": {"name": "Coolstream Thermal Inc.", "fye": "1231", "market": "us"},
    "ARVL": {"name": "Aravalli Cables Limited", "fye": "0331", "market": "in"},
}

DISTRACTORS = [
    "The Board authorized a new share repurchase program of up to $2.0 billion.",
    "We declared a quarterly dividend of $0.42 per share, payable next month.",
    "Diluted earnings per share were $1.87, up 14% from a year ago.",
    "Our stock price rose 23% during the quarter, and two analysts upgraded their ratings to buy.",
]


@dataclass
class Planted:
    fact_type: str
    subject_key: str
    unit: str
    quote: str
    value: str | None = None  # scaled amount as a decimal string
    low: str | None = None
    high: str | None = None
    written: dict[str, Any] = field(default_factory=dict)  # what a model reads off the quote (value, scale_word)
    period_label: str | None = None
    counterparty: str | None = None
    currency: str | None = None
    status: str = "verified"  # the Verify-1 outcome with a correct extraction


def money(rnd: random.Random, lo: float, hi: float, step: float = 0.5) -> Decimal:
    n = int((hi - lo) / step)
    return Decimal(str(lo)) + Decimal(str(step)) * rnd.randint(0, n)


def fmt(d: Decimal) -> str:
    s = f"{d:f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def b(x: Decimal) -> str:
    return str(x * Decimal(10) ** 9)


def m(x: Decimal) -> str:
    return str(x * Decimal(10) ** 6)


# ---------------------------------------------------------------- the planted facts, per document


def facts_for(rnd: random.Random) -> dict[str, list[Planted]]:
    capex_q1 = money(rnd, 70, 90)
    capex_q2 = capex_q1 + money(rnd, 2, 10)
    capex_rep = money(rnd, 15, 25, 0.1)
    rpo = money(rnd, 180, 260, 1)
    lease = money(rnd, 90, 140, 1)
    purchase = money(rnd, 30, 60, 1)
    mw_new = rnd.randint(4, 9) * 100
    backlog = money(rnd, 12, 20, 0.1)
    backlog_dc = money(rnd, 3, 6, 0.1)
    lead_tx = rnd.randint(110, 150)
    lead_sg = rnd.randint(40, 70)
    load_gw = money(rnd, 20, 40, 0.5)
    ppa_mw = rnd.randint(3, 8) * 100
    top1 = rnd.randint(25, 45)
    order_m = money(rnd, 200, 600, 5)
    price_pct = rnd.randint(5, 12)
    cap_sqft = rnd.randint(3, 9) * 100_000
    inr_cr = rnd.randint(300, 900)
    export_pct = rnd.randint(25, 45)
    guid_lo = money(rnd, 70, 80)
    guid_hi = guid_lo + 5
    return {
        "nmbs_10q_q1.htm": [
            Planted(
                "capex_guidance",
                "capex_guidance:FY2027",
                "usd",
                f"We expect capital expenditures of approximately ${fmt(capex_q1)} billion in fiscal 2027, "
                "driven by data center capacity for AI workloads.",
                value=b(capex_q1),
                written={"value": fmt(capex_q1), "scale_word": "billion"},
                period_label="fiscal 2027",
            ),
            Planted(
                "capex_reported",
                "capex_reported:Q1FY2027",
                "usd",
                f"Capital expenditures were ${fmt(capex_rep)} billion in the first quarter of fiscal 2027, "
                "primarily for servers, network equipment and data center construction.",
                value=b(capex_rep),
                written={"value": fmt(capex_rep), "scale_word": "billion"},
                period_label="first quarter of fiscal 2027",
            ),
            Planted(
                "rpo",
                "rpo:total",
                "usd",
                f"Remaining performance obligations were ${fmt(rpo)} billion as of September 30, 2026, "
                "reflecting multi-year commitments for AI infrastructure and data center services.",
                value=b(rpo),
                written={"value": fmt(rpo), "scale_word": "billion"},
            ),
            Planted(
                "commitment_lease",
                "lease_not_commenced:total",
                "usd",
                f"We have additional data center leases that have not yet commenced with future lease payments "
                f"of ${fmt(lease)} billion.",
                value=b(lease),
                written={"value": fmt(lease), "scale_word": "billion"},
            ),
        ],
        "nmbs_10q_q2.htm": [
            Planted(
                "capex_guidance",
                "capex_guidance:FY2027",
                "usd",
                f"We now expect capital expenditures of approximately ${fmt(capex_q2)} billion in fiscal 2027, "
                "an increase from our prior outlook due to accelerating AI demand.",
                value=b(capex_q2),
                written={"value": fmt(capex_q2), "scale_word": "billion"},
                period_label="fiscal 2027",
            ),
            Planted(
                "commitment_purchase",
                "purchase_obligations:total",
                "usd",
                f"Purchase obligations for compute capacity and network equipment totaled ${fmt(purchase)} "
                "billion, most of which we expect to pay within two years.",
                value=b(purchase),
                written={"value": fmt(purchase), "scale_word": "billion"},
            ),
            Planted(
                "capacity_addition",
                "capacity:mw:site_ohio_campus",
                "mw",
                f"We plan to add {mw_new} MW of data center capacity at our Ohio campus by the end of calendar 2027.",
                value=str(mw_new),
                written={"value": str(mw_new), "scale_word": None},
            ),
        ],
        "volt_10q.htm": [
            Planted(
                "backlog",
                "backlog:total",
                "usd",
                f"Total backlog reached ${fmt(backlog)} billion at quarter end, a record for the company.",
                value=b(backlog),
                written={"value": fmt(backlog), "scale_word": "billion"},
            ),
            Planted(
                "backlog",
                "backlog:data_center",
                "usd",
                f"Backlog from data center customers was ${fmt(backlog_dc)} billion, up from the prior year.",
                value=b(backlog_dc),
                written={"value": fmt(backlog_dc), "scale_word": "billion"},
            ),
            Planted(
                "lead_time",
                "lead_time:large_power_transformers",
                "weeks",
                f"Lead times for large power transformers extended to {lead_tx} weeks during the quarter.",
                value=str(lead_tx),
                written={"value": str(lead_tx), "scale_word": None},
            ),
            Planted(
                "customer_concentration",
                "customer_concentration:top1",
                "percent",
                f"Our largest customer, a hyperscale data center operator, accounted for {top1}% of revenue in "
                "the quarter.",
                value=str(top1),
                written={"value": str(top1), "scale_word": None},
            ),
            Planted(
                "supply_link",
                "link:nimbus_compute",
                "other",
                "We entered into a multi-year agreement to supply power transformers and switchgear to Nimbus "
                "Compute for its AI data center campuses.",
                counterparty="Nimbus Compute",
            ),
        ],
        "kyst_10q.htm": [
            Planted(
                "utility_load",
                "large_load:pipeline_gw",
                "gw",
                f"Our large-load interconnection pipeline, mostly data center requests, grew to {fmt(load_gw)} GW "
                "as of June 30, 2026.",
                value=fmt(load_gw),
                written={"value": fmt(load_gw), "scale_word": None},
            ),
            Planted(
                "commitment_ppa",
                "ppa:nimbus_compute:ohio",
                "mw",
                f"We signed a 15-year power purchase agreement with Nimbus Compute for {ppa_mw} MW to serve its "
                "Ohio data center campus.",
                value=str(ppa_mw),
                written={"value": str(ppa_mw), "scale_word": None},
                counterparty="Nimbus Compute",
            ),
        ],
        "clst_pr_order.htm": [
            Planted(
                "order_win",
                "order_win:nimbus_cooling",
                "usd",
                f"Coolstream Thermal received an order valued at ${fmt(order_m)} million from Nimbus Compute for "
                "liquid cooling systems for AI data centers.",
                value=m(order_m),
                written={"value": fmt(order_m), "scale_word": "million"},
                counterparty="Nimbus Compute",
            ),
            Planted(
                "price_increase",
                "price_increase:cooling_units",
                "percent",
                f"Effective January 1, the company will raise list prices on data center cooling units by "
                f"{price_pct}%.",
                value=str(price_pct),
                written={"value": str(price_pct), "scale_word": None},
            ),
        ],
        "volt_pr_plant.htm": [
            Planted(
                "capacity_addition",
                "capacity:sq_ft:texas_transformer_plant",
                "sq_ft",
                f"Voltara will build a {cap_sqft:,} square foot transformer factory in Texas to expand capacity "
                "for grid and data center customers.",
                value=str(cap_sqft),
                written={"value": f"{cap_sqft}", "scale_word": None},
            ),
            Planted(
                "lead_time",
                "lead_time:switchgear",
                "weeks",
                f"Current lead times for medium-voltage switchgear are {lead_sg} weeks.",
                value=str(lead_sg),
                written={"value": str(lead_sg), "scale_word": None},
            ),
        ],
        "nmbs_pr_guidance.htm": [
            Planted(
                "capex_guidance",
                "capex_guidance:FY2028",
                "usd",
                f"For fiscal 2028, Nimbus expects capital expenditures of ${fmt(guid_lo)} billion to "
                f"${fmt(guid_hi)} billion.",
                low=b(guid_lo),
                high=b(guid_hi),
                written={"value_low": fmt(guid_lo), "value_high": fmt(guid_hi), "scale_word": "billion"},
                value=str((Decimal(b(guid_lo)) + Decimal(b(guid_hi))) / 2),
                period_label="fiscal 2028",
            ),
            Planted(
                "new_segment",
                "new_segment:ai_infrastructure",
                "other",
                "Beginning next quarter, Nimbus will report AI Infrastructure Services as a new reportable segment.",
            ),
        ],
        "arvl_pr_order.htm": [
            Planted(
                "order_win",
                "order_win:us_data_center_cables",
                "usd",
                f"Aravalli Cables has received an export order worth Rs {inr_cr} crore for high-voltage cables for "
                "a data center project in the United States.",
                value=str(inr_cr * 10**7),
                written={"value": str(inr_cr), "scale_word": None},
                currency="INR",
                status="verified",  # an Indian company's own currency (docs/SPEC_ISSUES.md 31 option b, 58)
            ),
            Planted(
                "export_exposure",
                "export_exposure:share_pct",
                "percent",
                f"Exports accounted for {export_pct}% of revenue in the first half of fiscal 2027.",
                value=str(export_pct),
                written={"value": str(export_pct), "scale_word": None},
            ),
        ],
        "kyst_10k_2025_risk.htm": [],
        "kyst_10k_2026_risk.htm": [],
        "nmbs_investor_day.pdf": [
            Planted(
                "capacity_addition",
                "capacity:gw:global_ai_campuses",
                "gw",
                "We plan to bring 2.4 GW of new AI data center capacity online across our global campuses by 2028.",
                value="2.4",
                written={"value": "2.4", "scale_word": None},
            ),
        ],
        "volt_investor_pres.pdf": [
            Planted(
                "lead_time",
                "lead_time:gas_turbines",
                "months",
                "Customers now face lead times of 30 to 36 months for large gas turbines.",
                low="30",
                high="36",
                value="33",
                written={"value_low": "30", "value_high": "36", "scale_word": None},
            ),
        ],
    }


# ---------------------------------------------------------------- document bodies


def para(text: str) -> str:
    return f'<p style="margin:0">{escape(text)}</p>'


def ten_q(title: str, company: str, mdna: list[str], notes: list[tuple[str, list[str]]], rnd: random.Random) -> str:
    toc = ("<table><tr><td>Item 1.</td><td>Financial Statements</td><td>3</td></tr>"
           "<tr><td>Item 2.</td><td>Management's Discussion and Analysis</td><td>18</td></tr>"
           "<tr><td>Item 1A.</td><td>Risk Factors</td><td>31</td></tr></table>")  # fmt: skip
    hidden = ('<div style="display:none"><ix:header><ix:hidden><ix:nonNumeric name="dei:EntityRegistrantName">'
              f"{escape(company)}</ix:nonNumeric><ix:nonFraction name=\"us-gaap:Revenues\">"
              f"{rnd.randint(10**9, 9 * 10**9)}</ix:nonFraction></ix:hidden></ix:header></div>")  # fmt: skip
    head = f"<html><head><title>{escape(title)}</title><style>p {{ font-family: serif; }}</style></head><body>"
    parts = [head,
             hidden, f"<p><b>{escape(company)}</b></p>", para(f"FORM 10-Q · {title}"), toc,
             "<p>PART I — FINANCIAL INFORMATION</p>", "<p>Item 1. Financial Statements</p>"]  # fmt: skip
    parts.append("<table><tr><th>(in millions)</th><th>Three months ended</th></tr>"
                 f"<tr><td>Revenue</td><td>$</td><td>{rnd.randint(4000, 9000):,}</td></tr>"
                 f"<tr><td>Operating income</td><td>$</td><td>{rnd.randint(800, 2000):,}</td></tr>"
                 "</table>")  # fmt: skip
    for k, (title_n, body) in enumerate(notes, start=3):
        parts.append(f"<p><b>Note {k} — {escape(title_n)}</b></p>")
        parts += [para(s) for s in body]
    parts.append("<p>Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations</p>")
    parts += [para(s) for s in mdna]
    parts.append("<p>Item 3. Quantitative and Qualitative Disclosures About Market Risk</p>")
    parts.append(para("Our exposure to market risk has not changed materially since our annual report."))
    parts.append("<p>PART II — OTHER INFORMATION</p><p>Item 1A. Risk Factors</p>")
    parts.append(para("There have been no material changes to the risk factors disclosed in our annual report."))
    parts.append("<script>window.x = 1;</script></body></html>")
    return "\n".join(parts)


def press_release(headline: str, company: str, city: str, body: list[str]) -> str:
    parts = [f"<html><head><title>{escape(headline)}</title></head><body>", f"<h1>{escape(headline)}</h1>",
             para(f"{city} — {company} today announced the following.")]  # fmt: skip
    parts += [para(s) for s in body]
    parts.append(para("About the company: this is a fictional company created for testing."))
    parts.append("</body></html>")
    return "\n".join(parts)


FILLER = [
    "Revenue growth reflected higher demand for AI infrastructure and data center capacity across our markets.",
    "Operating expenses increased as we invested in capacity, data center operations and engineering headcount.",
    "We continue to monitor supply chain conditions, including lead time trends for transformers and switchgear.",
    "Liquidity remained strong, and we believe cash flows and available credit will fund our capital expenditures.",
]


def risk_section(version: int) -> str:
    base = [
        "Our operations depend on the reliable delivery of power to our customers, and extreme weather events could "
        "disrupt our transmission and distribution systems and increase our costs significantly.",
        "We depend on third-party suppliers for large power transformers and switchgear, and supply shortages could "
        "delay the interconnection of new customer loads and increase our capital expenditures.",
        "Changes in federal and state tax law could affect our effective tax rate and cash flows in ways that are "
        "difficult to predict today.",
        "Regulatory decisions on our rate cases determine the returns we may earn on our investments, and adverse "
        "decisions could reduce our earnings and cash flows.",
        "Cyber attacks on our systems or those of our vendors could disrupt operations and expose us to liability, "
        "regulatory penalties and reputational harm.",
    ]
    if version == 2:
        base[1] = ("We depend on third-party suppliers for large power transformers, gas turbines and switchgear, and "
                   "lead times for transformers now exceed two years, which could delay the interconnection of data "
                   "center loads and increase our capital expenditures.")  # fmt: skip
        del base[2]
        base.insert(1, "A significant share of our expected load growth comes from data center customers whose "
                       "demand for AI computing may not materialize as forecast, which could leave us with stranded "
                       "generation and transmission investments.")  # fmt: skip
    parts = ["<html><head><title>Form 10-K</title></head><body>", "<p>Keystone Power &amp; Light Co.</p>",
             "<p>PART I</p>", "<p>Item 1. Business</p>",
             para("We are a regulated electric utility serving customers across three states."),
             "<p>Item 1A. Risk Factors</p>", *[para(t) for t in base], "<p>Item 1B. Unresolved Staff Comments</p>",
             para("None."), "</body></html>"]  # fmt: skip
    return "\n".join(parts)


# ---------------------------------------------------------------- a minimal PDF writer (Helvetica, one line per Tj)


def pdf(pages: list[list[str]]) -> bytes:
    objs: list[bytes] = []

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    page_ids = []
    pages_id = len(objs) + 2 * len(pages) + 1
    for lines in pages:
        ops = ["BT", "/F1 10 Tf", "12 TL", "54 740 Td"]
        for line in lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({safe}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("cp1252")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 %d 0 R "
                            b">> >> /Contents %d 0 R >>" % (pages_id, font, content)))  # fmt: skip
    kids = " ".join(f"{p} 0 R" for p in page_ids).encode()
    assert add(b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(page_ids)) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog, xref)
    return bytes(out)


def wrap(text: str, width: int = 100) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return [*lines, cur] if cur else lines


# ---------------------------------------------------------------- build


def build(seed: int = SEED) -> dict[str, Any]:
    rnd = random.Random(seed)  # noqa: S311 — fixture data, not security
    planted = facts_for(rnd)
    q = {name: [p.quote for p in facts] for name, facts in planted.items()}
    docs: dict[str, bytes] = {}
    docs["nmbs_10q_q1.htm"] = ten_q("Quarter ended September 30, 2026", COMPANIES["NMBS"]["name"],
                                    [FILLER[0], q["nmbs_10q_q1.htm"][0], q["nmbs_10q_q1.htm"][1], DISTRACTORS[0],
                                     FILLER[1]],
                                    [("Revenue", [q["nmbs_10q_q1.htm"][2], DISTRACTORS[2]]),
                                     ("Leases", [FILLER[3], q["nmbs_10q_q1.htm"][3]])], rnd).encode()  # fmt: skip
    docs["nmbs_10q_q2.htm"] = ten_q("Quarter ended December 31, 2026", COMPANIES["NMBS"]["name"],
                                    [q["nmbs_10q_q2.htm"][0], FILLER[0], q["nmbs_10q_q2.htm"][2], DISTRACTORS[1]],
                                    [("Commitments and Contingencies", [q["nmbs_10q_q2.htm"][1], FILLER[3]])],
                                    rnd).encode()  # fmt: skip
    docs["volt_10q.htm"] = ten_q("Quarter ended June 30, 2026", COMPANIES["VOLT"]["name"],
                                 [FILLER[2], q["volt_10q.htm"][0], q["volt_10q.htm"][1], q["volt_10q.htm"][2],
                                  DISTRACTORS[3], q["volt_10q.htm"][3], q["volt_10q.htm"][4]],
                                 [("Debt", [FILLER[3]])], rnd).encode()  # fmt: skip
    docs["kyst_10q.htm"] = ten_q(
        "Quarter ended June 30, 2026",
        COMPANIES["KYST"]["name"],
        [FILLER[0], q["kyst_10q.htm"][0], FILLER[2]],
        [("Commitments and Contingencies", [q["kyst_10q.htm"][1], FILLER[3]])],
        rnd,
    ).encode()
    docs["clst_pr_order.htm"] = press_release(
        "Coolstream Thermal Wins Liquid Cooling Order for AI Data Centers",
        COMPANIES["CLST"]["name"],
        "BOSTON",
        [q["clst_pr_order.htm"][0], FILLER[0], q["clst_pr_order.htm"][1], DISTRACTORS[1]],
    ).encode()
    docs["volt_pr_plant.htm"] = press_release(
        "Voltara to Build Transformer Factory in Texas",
        COMPANIES["VOLT"]["name"],
        "HOUSTON",
        [q["volt_pr_plant.htm"][0], FILLER[2], q["volt_pr_plant.htm"][1], DISTRACTORS[0]],
    ).encode()
    docs["nmbs_pr_guidance.htm"] = press_release(
        "Nimbus Compute Reports Results and Issues Fiscal 2028 Outlook", COMPANIES["NMBS"]["name"], "SEATTLE",
        [FILLER[0], q["nmbs_pr_guidance.htm"][0], q["nmbs_pr_guidance.htm"][1], DISTRACTORS[2],
         DISTRACTORS[3]]).encode()  # fmt: skip
    docs["arvl_pr_order.htm"] = press_release(
        "Aravalli Cables Bags Export Order for US Data Center",
        COMPANIES["ARVL"]["name"],
        "JAIPUR",
        [q["arvl_pr_order.htm"][0], q["arvl_pr_order.htm"][1], FILLER[2]],
    ).encode()
    docs["kyst_10k_2025_risk.htm"] = risk_section(1).encode()
    docs["kyst_10k_2026_risk.htm"] = risk_section(2).encode()
    docs["nmbs_investor_day.pdf"] = pdf([
        ["Nimbus Compute Corp. Investor Day 2026", "", *wrap(FILLER[0]), *wrap(DISTRACTORS[0])],
        ["AI infrastructure build-out", "", *wrap(q["nmbs_investor_day.pdf"][0]), *wrap(FILLER[1]),
         "Data center capacity, GPU clusters and networking remain our largest capital programs."],
    ])  # fmt: skip
    docs["volt_investor_pres.pdf"] = pdf([
        ["Voltara Grid Systems Investor Presentation", "", *wrap(FILLER[2]), *wrap(DISTRACTORS[3])],
        ["Supply and demand for power equipment", "", *wrap(q["volt_investor_pres.pdf"][0]),
         "Transformer, turbine and switchgear capacity is sold out through 2027 across the industry.",
         *wrap(FILLER[0])],
    ])  # fmt: skip
    meta = {
        "nmbs_10q_q1.htm": ("NMBS", "10-Q", "2026-10-28T20:05:00+00:00", "Form 10-Q Q1 FY2027"),
        "nmbs_10q_q2.htm": ("NMBS", "10-Q", "2027-01-27T21:10:00+00:00", "Form 10-Q Q2 FY2027"),
        "volt_10q.htm": ("VOLT", "10-Q", "2026-07-30T20:15:00+00:00", "Form 10-Q Q2 2026"),
        "kyst_10q.htm": ("KYST", "10-Q", "2026-08-06T20:30:00+00:00", "Form 10-Q Q2 2026"),
        "clst_pr_order.htm": ("CLST", "EX-99.1", "2026-09-15T12:00:00+00:00", "Order press release"),
        "volt_pr_plant.htm": ("VOLT", "EX-99.1", "2026-09-10T12:30:00+00:00", "Texas plant press release"),
        "nmbs_pr_guidance.htm": ("NMBS", "EX-99.1", "2027-07-29T20:05:00+00:00", "Fiscal 2028 outlook"),
        "arvl_pr_order.htm": ("ARVL", "press_release", "2026-09-18T10:15:00+00:00", "Export order announcement"),
        "kyst_10k_2025_risk.htm": ("KYST", "10-K", "2025-02-20T21:00:00+00:00", "Form 10-K 2024"),
        "kyst_10k_2026_risk.htm": ("KYST", "10-K", "2026-02-19T21:00:00+00:00", "Form 10-K 2025"),
        "nmbs_investor_day.pdf": ("NMBS", "presentation", "2026-11-12T15:00:00+00:00", "Investor Day 2026"),
        "volt_investor_pres.pdf": ("VOLT", "presentation", "2026-09-22T13:00:00+00:00", "Investor presentation"),
    }
    truth = {
        "seed": seed,
        "companies": COMPANIES,
        "distractors": DISTRACTORS,
        "documents": [
            {
                "file": name,
                "ticker": meta[name][0],
                "kind": meta[name][1],
                "published_at": meta[name][2],
                "title": meta[name][3],
                "facts": [p.__dict__ for p in planted[name]],
            }
            for name in sorted(docs)
        ],
        "risk_changes": {
            "from": "kyst_10k_2025_risk.htm",
            "to": "kyst_10k_2026_risk.htm",
            "expected": {"added": 1, "removed": 1},
        },  # fmt: skip
    }
    return {"docs": docs, "truth": truth}


def main() -> None:
    out = build()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, body in out["docs"].items():
        (OUT / name).write_bytes(body)
    (OUT / "ground_truth.json").write_text(json.dumps(out["truth"], indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"F-SYN: {len(out['docs'])} documents, "
          f"{sum(len(d['facts']) for d in out['truth']['documents'])} planted facts -> {OUT}")  # fmt: skip


if __name__ == "__main__":
    main()

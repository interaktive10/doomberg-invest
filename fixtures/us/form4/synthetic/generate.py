"""Writes the synthetic insider cluster of F-F4 (BRIEF Appendix fixtures): a made-up issuer (CIK 0009999901,
"Synthetic Cluster Corp") whose insiders file six Form 4s in spring 2025. `python fixtures/us/form4/synthetic/generate.py`

What it exercises (M2-03 here; S7 in M4):
- 000001 director, unplanned P $150,000 and 000002 CFO, unplanned P $124,000 (+ an option grant, derivative): the
  cluster, 2 distinct insiders, $274,000 within 60 days;
- 000003 CEO, P $80,000 with the 10b5-1 checkbox marked -> planned;
- 000004 joint filers (fund + its GP, one person for S7), P $32,200 under a 10b5-1 plan named only in a footnote;
- 000005 the director again, P $16,500 (below S7's $25k per-buy minimum); 000006 the CFO's sale (code S).
Acceptance times are US Eastern in the SGML header, like real submissions.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent
ISSUER = ("0009999901", "SYNTHETIC CLUSTER CORP", "ZZZC")


def owner(cik: str, name: str, director: bool = False, officer: str | None = None, ten_pct: bool = False) -> str:
    title = f"\n            <officerTitle>{officer}</officerTitle>" if officer else ""
    return f"""    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>{cik}</rptOwnerCik>
            <rptOwnerName>{name}</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>{str(director).lower()}</isDirector>
            <isOfficer>{str(officer is not None).lower()}</isOfficer>
            <isTenPercentOwner>{str(ten_pct).lower()}</isTenPercentOwner>
            <isOther>false</isOther>{title}
        </reportingOwnerRelationship>
    </reportingOwner>"""


def nd_tx(day: str, code: str, shares: int, price: str, ad: str, footnote: str | None = None) -> str:
    fn = f'\n                <footnoteId id="{footnote}"/>' if footnote else ""
    return f"""        <nonDerivativeTransaction>
            <securityTitle><value>Common Stock</value></securityTitle>
            <transactionDate><value>{day}</value></transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>{code}</transactionCode>
                <equitySwapInvolved>false</equitySwapInvolved>{fn}
            </transactionCoding>
            <transactionAmounts>
                <transactionShares><value>{shares}</value></transactionShares>
                <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
        </nonDerivativeTransaction>"""


def option_grant(day: str, shares: int) -> str:
    return f"""    <derivativeTable>
        <derivativeTransaction>
            <securityTitle><value>Stock Option (right to buy)</value></securityTitle>
            <conversionOrExercisePrice><value>15.50</value></conversionOrExercisePrice>
            <transactionDate><value>{day}</value></transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>A</transactionCode>
                <equitySwapInvolved>false</equitySwapInvolved>
            </transactionCoding>
            <transactionAmounts>
                <transactionShares><value>{shares}</value></transactionShares>
                <transactionPricePerShare><value>0</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
        </derivativeTransaction>
    </derivativeTable>"""


def submission(seq: int, accepted_et: str, period: str, owners: list[str], txs: list[str], checkbox: bool = False,
               derivative: str = "", footnotes: dict[str, str] | None = None) -> str:  # fmt: skip
    acc = f"{ISSUER[0]}-25-{seq:06d}"
    notes = "".join(f'\n        <footnote id="{k}">{v}</footnote>' for k, v in (footnotes or {}).items())
    body = "\n".join(txs)
    return f"""<SEC-DOCUMENT>{acc}.txt : {accepted_et[:8]}
<SEC-HEADER>{acc}.hdr.sgml : {accepted_et[:8]}
<ACCEPTANCE-DATETIME>{accepted_et}
ACCESSION NUMBER:\t\t{acc}
CONFORMED SUBMISSION TYPE:\t4
PUBLIC DOCUMENT COUNT:\t\t1
CONFORMED PERIOD OF REPORT:\t{period.replace("-", "")}
FILED AS OF DATE:\t\t{accepted_et[:8]}
</SEC-HEADER>
<DOCUMENT>
<TYPE>4
<SEQUENCE>1
<FILENAME>ownership.xml
<TEXT>
<XML>
<?xml version="1.0"?>
<ownershipDocument>
    <schemaVersion>X0508</schemaVersion>
    <documentType>4</documentType>
    <periodOfReport>{period}</periodOfReport>
    <issuer>
        <issuerCik>{ISSUER[0]}</issuerCik>
        <issuerName>{ISSUER[1]}</issuerName>
        <issuerTradingSymbol>{ISSUER[2]}</issuerTradingSymbol>
    </issuer>
{chr(10).join(owners)}
    <aff10b5One>{str(checkbox).lower()}</aff10b5One>
    <nonDerivativeTable>
{body}
    </nonDerivativeTable>
{derivative}
    <footnotes>{notes}
    </footnotes>
</ownershipDocument>
</XML>
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""


FILINGS = {
    1: submission(1, "20250310160500", "2025-03-07", [owner("0009999911", "DOE JANE", director=True)],
                  [nd_tx("2025-03-07", "P", 10000, "15.00", "A", "F1")],
                  footnotes={"F1": "Weighted average purchase price; prices ranged from $14.95 to $15.05."}),
    2: submission(2, "20250320170000", "2025-03-18",
                  [owner("0009999912", "ROE RICHARD", officer="Chief Financial Officer")],
                  [nd_tx("2025-03-18", "P", 8000, "15.50", "A")], derivative=option_grant("2025-03-18", 20000)),
    3: submission(3, "20250401163000", "2025-03-28",
                  [owner("0009999913", "POE ALEX", director=True, officer="Chief Executive Officer")],
                  [nd_tx("2025-03-28", "P", 5000, "16.00", "A")], checkbox=True),
    4: submission(4, "20250415180000", "2025-04-11",
                  [owner("0009999914", "EXAMPLE CAPITAL FUND LP", ten_pct=True),
                   owner("0009999915", "EXAMPLE CAPITAL GP LLC", ten_pct=True)],
                  [nd_tx("2025-04-11", "P", 2000, "16.10", "A", "F1")],
                  footnotes={"F1": "These shares were purchased pursuant to a Rule 10b5-1 trading plan adopted by "
                                   "the Reporting Persons on November 12, 2024."}),
    5: submission(5, "20250421163000", "2025-04-17",
                  [owner("0009999911", "DOE JANE", director=True)],
                  [nd_tx("2025-04-17", "P", 1000, "16.50", "A")]),
    6: submission(6, "20250422170500", "2025-04-18",
                  [owner("0009999912", "ROE RICHARD", officer="Chief Financial Officer")],
                  [nd_tx("2025-04-18", "S", 3000, "16.75", "D")]),
}  # fmt: skip


if __name__ == "__main__":
    for seq, text in FILINGS.items():
        (OUT / f"{ISSUER[0]}-25-{seq:06d}.txt").write_text(text, encoding="utf-8")
    print(f"wrote {len(FILINGS)} synthetic Form 4 submissions to {OUT}")

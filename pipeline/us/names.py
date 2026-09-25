"""Company-name normalization shared by 13F CUSIP mapping and spin-off parent linking (BRIEF §4.2)."""

from __future__ import annotations

import re

_SUFFIXES = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LLC", "LP", "NV", "SA",
    "AG", "SE", "THE", "NEW", "DEL", "DE", "MD", "COM", "CL", "CLASS", "A", "B", "C",
}  # fmt: skip
NON_COMMON = re.compile(
    r"\b(PFD|PREF|PREFERRED|WTS?|WARRANTS?|RIGHTS?|RTS|NOTES?|DEBT|DBCV|SDCV|CONV|CONVERTIBLE|BONDS?"
    r"|OPTS?|OPTIONS?|PUTS?|CALLS?)\b|\*W\b|\bW EXP\b",
    re.IGNORECASE,
)
_UNIT = re.compile(r"\bUNITS?\b", re.IGNORECASE)
_PARTNERSHIP = re.compile(r"\b(COM|COMMON|LP|L P|PARTN\w*|PTN\w*|PARTNERSHIP)\b", re.IGNORECASE)


def non_common(title: str) -> bool:
    """A 13F TITLEOFCLASS that is not the common stock: preferred, warrants, rights, debt, options, and units other
    than partnership common units ("COM UNIT LTD PARTN" is an MLP's common equity; "UNIT 06/01/2027" is not)."""
    if NON_COMMON.search(title):
        return True
    return bool(_UNIT.search(title)) and not _PARTNERSHIP.search(title)


_ABBREV = {
    "HLDGS": "HOLDINGS", "HLDG": "HOLDING", "HLDNGS": "HOLDINGS", "SVCS": "SERVICES", "SVC": "SERVICE",
    "INDS": "INDUSTRIES", "MFG": "MANUFACTURING", "MATLS": "MATERIALS",
    "TECH": "TECHNOLOGY", "INTL": "INTERNATIONAL", "CTLS": "CONTROLS", "SYS": "SYSTEMS", "RLTY": "REALTY",
    "TR": "TRUST", "MTN": "MOUNTAIN", "GRP": "GROUP", "COMM": "COMMUNICATIONS", "ENTMT": "ENTERTAINMENT",
    "PPTYS": "PROPERTIES", "FINL": "FINANCIAL", "PHARMA": "PHARMACEUTICALS", "SOLTNS": "SOLUTIONS",
    "ELEC": "ELECTRIC", "NATL": "NATIONAL", "AMER": "AMERICA", "BANCORPORATION": "BANCORP", "LABS": "LABORATORIES",
}  # fmt: skip


def normalize_name(name: str) -> str:
    """Issuer/company name for matching: upper case, '&' -> AND, punctuation dropped, common abbreviations spelled
    out, legal suffixes and state tags (/DE/) removed."""
    s = name.upper().replace("&", " AND ")
    s = re.sub(r"/[A-Z]{2,3}/?", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\b([NLS]) ([VPA])\b", r"\1\2", s)  # "N V" -> NV, "L P" -> LP, "S A" -> SA
    words = [_ABBREV.get(w, w) for w in s.split()]
    while words and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)

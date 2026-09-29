"""GDELT DOC 2.0 API (BRIEF §2.7, §4.7 C4): how many news articles mention a company over the last 90 days. Free,
no key, candidates only, one request every 5 s (pipeline/net/http.py).

The query is the company's quoted short name, disambiguated with its ticker or "Inc" / "Ltd". GDELT answers errors
as plain text with HTTP 200 ("Please limit requests...", "phrase too short"); those raise GdeltError."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import quote

from pipeline.net.http import HttpClient

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
SUFFIXES = re.compile(
    r"(,?\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|l\.p|n\.v|s\.a|ag|se|holdings?"
    r"|group|the)\.?)+\s*$",
    re.IGNORECASE,
)


class GdeltError(Exception):
    """GDELT answered something other than a timeline."""


def short_name(name: str) -> str:
    """'Quanta Services, Inc.' -> 'Quanta Services'; 'KEI Industries Limited' -> 'KEI Industries'."""
    s = re.sub(r"\s+", " ", name.replace("&amp;", "&")).strip(" .,")
    s = SUFFIXES.sub("", s).strip(" .,")
    return s or name.strip()


def build_query(name: str, ticker: str | None, market: str) -> str:
    qualifier = "Ltd" if market == "in" else "Inc"
    terms = [t for t in (ticker, qualifier) if t and len(t) >= 3]  # GDELT rejects keywords under 3 characters
    phrase = f'"{short_name(name)}"'
    return f"{phrase} ({' OR '.join(terms)})" if len(terms) > 1 else f"{phrase} {terms[0]}" if terms else phrase


def timeline_url(query: str, days: int = 90) -> str:
    return f"{DOC_API}?query={quote(query)}&mode=timelinevolraw&timespan={days}d&format=json"


def parse_count(body: bytes) -> int:
    text = body.decode("utf-8", "replace").strip()
    if not text.startswith("{"):
        raise GdeltError(text[:200] or "empty response")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise GdeltError(f"bad JSON: {e}") from e
    series = doc.get("timeline") or []
    if not series:
        return 0
    return sum(int(p.get("value", 0)) for p in series[0].get("data", []))


@dataclass
class GdeltClient:
    http: HttpClient

    def article_count(self, name: str, ticker: str | None, market: str, days: int = 90) -> int:
        return parse_count(self.http.get_bytes(timeline_url(build_query(name, ticker, market), days), timeout=60.0))

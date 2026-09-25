"""BSE access: the fallback when NSE is stale (BRIEF §4.3).

BSE's servers want both Origin and Referer set to bseindia.com (docs/DOOMBERG_AUDIT.md §4.2). ≤ 1 request per 3 s
(pipeline/net/http.py ALLOWED_HOSTS). BSE answers a missing download (a holiday's bhavcopy) with HTTP 200 and its
HTML home page, so callers check the content, not only the status.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import httpx

from pipeline.net.http import HttpClient

BSE_HOME = "https://www.bseindia.com/"
HEADERS = {"Origin": "https://www.bseindia.com", "Referer": BSE_HOME}


class BseUnavailable(Exception):
    pass


def bhavcopy_url(d: date) -> str:
    """BSE's UDiFF common bhavcopy (same columns as NSE's)."""
    return f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"


@dataclass
class BseClient:
    http: HttpClient
    sleep: Callable[[float], None] = time.sleep
    backoff: tuple[float, ...] = (6.0, 12.0)

    def get(self, url: str, *, use_cache: bool = False) -> bytes:
        waits = iter(self.backoff)
        while True:
            try:
                return self.http.get_bytes(url, headers=HEADERS, use_cache=use_cache)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise
                wait = next(waits, None)
                if wait is None:
                    raise BseUnavailable(f"{e.response.status_code} {url}") from e
            except httpx.TransportError as e:
                wait = next(waits, None)
                if wait is None:
                    raise BseUnavailable(f"{type(e).__name__} {url}") from e
            self.sleep(wait)

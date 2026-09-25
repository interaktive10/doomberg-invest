"""NSE access (BRIEF §4.3 "Access rules"; docs/DOOMBERG_AUDIT.md §4 lessons from the old Doomberg).

- Browser headers plus a Referer; cookies from a warm-up request to the NSE home page, re-warmed every 600 s. A
  forced re-warm rebuilds the session, which drops cookies NSE has flagged. The home page itself is often refused
  to data-centre IPs while the APIs still answer, so a failed warm-up is not an error.
- ≤ 1 request per 3 s to NSE as a whole (www and nsearchives share one limit): pipeline/net/http.py's rate limiter.
- A block is a 401/403/429 response (NSE's CDN answers "Access Denied"). After a block: one retry on a rebuilt
  session, then exponential backoff. **3 consecutive blocks** make the client stale for the rest of the run:
  every later call raises NseStale at once, and the caller marks source_health 'nse' stale and switches to BSE,
  then to the manual CSV import (pipeline/india/manual_import.py).
- 5xx answers and timeouts back off and retry; a URL that still fails after the retries is a failure, and **3
  consecutive failed URLs** also make the client stale (review F9 on M3: a sustained outage must not spend the
  run's time budget one URL at a time).
- `deadline` (a clock value): the run's time budget. After it the client makes no request (NseDeadline) and the
  runs leave the rest queued for the next run, so the job never reaches its timeout.
- NSE also answers 403 for an archive file that doesn't exist (a holiday's bhavcopy), so callers ask NSE only for
  files that exist (the bhavcopy run checks the trading day with BSE first).
- Immutable archive files (bhavcopy, XBRL) are cached on disk (use_cache).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from pipeline.net.http import HttpClient, MockNotRegistered

NSE_HOME = "https://www.nseindia.com/"
NSE_API = "https://www.nseindia.com/api"
NSE_ARCHIVES = "https://nsearchives.nseindia.com"
WARM_EVERY_S = 600.0
BLOCK_STATUSES = frozenset({401, 403, 429})
MAX_CONSECUTIVE_BLOCKS = 3
MAX_CONSECUTIVE_FAILURES = 3  # URLs that still failed (5xx, timeout) after their retries


class NseBlocked(Exception):
    """A request failed with a block status (or kept failing) but the client is not stale yet."""


class NseStale(NseBlocked):
    """3 consecutive blocks (or failed URLs): NSE is treated as unavailable for the rest of the run."""


class NseDeadline(NseBlocked):
    """The run's time budget is spent: no more NSE requests this run (not a fault of NSE's)."""


@dataclass
class NseClient:
    http: HttpClient
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    backoff: tuple[float, ...] = (6.0, 12.0, 24.0)  # waits between attempts after the re-warm retry
    consecutive_blocks: int = 0
    consecutive_failures: int = 0
    stale: bool = False
    blocks: list[str] = field(default_factory=list)  # "status url", for source_health.last_error
    deadline: float | None = None  # clock() value after which no request is made
    _warmed_at: float | None = None

    @property
    def out_of_time(self) -> bool:
        return self.deadline is not None and self.clock() >= self.deadline

    @property
    def unavailable(self) -> bool:
        """Stale or out of time: loops stop and leave the rest queued."""
        return self.stale or self.out_of_time

    def _warm(self, force: bool = False) -> None:
        now = self.clock()
        if not force and self._warmed_at is not None and now - self._warmed_at < WARM_EVERY_S:
            return
        if force:
            self.http.reset_session()
        try:
            self.http.get_bytes(NSE_HOME, headers={"Referer": NSE_HOME})
        except (httpx.HTTPError, MockNotRegistered):
            pass  # the APIs often answer without the home page's cookies
        self._warmed_at = now

    def _block(self, url: str, status: int) -> None:
        self.consecutive_blocks += 1
        self.blocks.append(f"{status} {url}")
        if self.consecutive_blocks >= MAX_CONSECUTIVE_BLOCKS:
            self.stale = True

    def _failed(self, url: str, reason: str) -> NseBlocked:
        """A URL that kept failing after its retries (5xx, timeout)."""
        self.consecutive_failures += 1
        self.blocks.append(f"{reason} {url}")
        if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self.stale = True
            return NseStale(f"NSE stale after {MAX_CONSECUTIVE_FAILURES} consecutive failed requests ({url})")
        return NseBlocked(f"{reason} {url}")

    def get(self, url: str, *, referer: str = NSE_HOME, use_cache: bool = False) -> bytes:
        """GET an NSE API or archive URL. Raises NseStale (source unavailable this run), NseBlocked (this URL kept
        failing), or httpx.HTTPStatusError for other client errors (404)."""
        if self.stale:
            raise NseStale(f"NSE is stale after 3 consecutive blocks or failures: {self.blocks[-3:]}")
        if self.out_of_time:
            raise NseDeadline(f"the run's time budget is spent ({url})")
        self._warm()
        headers = {"Referer": referer, "Accept": "application/json, text/plain, */*"}
        rewarmed = False
        waits = iter(self.backoff)
        while True:
            try:
                body = self.http.get_bytes(url, headers=headers, use_cache=use_cache)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status not in BLOCK_STATUSES and status < 500:
                    raise
                if status in BLOCK_STATUSES:
                    self._block(url, status)
                    if self.stale:
                        raise NseStale(f"NSE stale after {MAX_CONSECUTIVE_BLOCKS} consecutive blocks ({url})") from e
                    if not rewarmed:
                        rewarmed = True
                        self._warm(force=True)
                        continue
                wait = next(waits, None)
                if wait is None:
                    raise self._failed(url, str(status)) from e
                self.sleep(wait)
                continue
            except httpx.TransportError as e:
                wait = next(waits, None)
                if wait is None:
                    raise self._failed(url, type(e).__name__) from e
                self.sleep(wait)
                continue
            self.consecutive_blocks = self.consecutive_failures = 0
            return body

    def api(self, path: str, referer: str = NSE_HOME) -> bytes:
        """An NSE JSON API, e.g. api("corporate-announcements?index=equities")."""
        return self.get(f"{NSE_API}/{path}", referer=referer)

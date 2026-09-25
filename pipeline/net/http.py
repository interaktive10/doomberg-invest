"""The one HTTP client for the pipeline (BRIEF §2.3, §2.7, §4.3).

- Domain allowlist: any host not listed raises DomainNotAllowed before a socket opens.
- Minimum interval between requests per site (SEC <= 8 req/s, NSE 1 per 3 s, Stooq 1 per 2 s, ...). A site's hosts
  share one limit: www.nseindia.com and nsearchives.nseindia.com are one NSE (review F6 on M3).
- Optional on-disk cache keyed by URL.
- MOCK_EXTERNALS=true: no network at all; requests are served from registered mock responses, or raise.

Old-Doomberg lesson (docs/DOOMBERG_AUDIT.md §4): per-source cookie warm-up, one retry after re-warm on 401/403,
and "stale cache beats no data" are the patterns that kept its NSE/BSE feeds alive. The NSE client (M3) builds
on this module rather than on raw httpx.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from pipeline.settings import Settings


class DomainNotAllowed(Exception):
    """Raised for any request to a host outside ALLOWED_HOSTS."""


class MockNotRegistered(Exception):
    """MOCK_EXTERNALS is on and no mock response matches the URL."""


# host -> minimum seconds between requests to that host's site (BRIEF §2.7 fair-access rules; see rate_key).
ALLOWED_HOSTS: dict[str, float] = {
    "www.sec.gov": 0.125,
    "data.sec.gov": 0.125,
    "efts.sec.gov": 0.125,
    "www.nseindia.com": 3.0,
    "nsearchives.nseindia.com": 3.0,
    "archives.nseindia.com": 3.0,
    "www.bseindia.com": 3.0,
    "api.bseindia.com": 3.0,
    "stooq.com": 2.0,
    "api.gdeltproject.org": 5.0,  # GDELT asks for at most one request every 5 s
    "api.stlouisfed.org": 0.5,
    "api.eia.gov": 0.5,
    "generativelanguage.googleapis.com": 0.0,
    "api.groq.com": 0.0,
    "openrouter.ai": 0.0,
    "api.github.com": 0.0,
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def rate_key(host: str) -> str:
    """The site a host belongs to (its last two labels): hosts of one site share one rate limit."""
    return ".".join(host.split(".")[-2:])


def check_allowed(url: str) -> str:
    scheme = urlsplit(url).scheme
    host = host_of(url)
    if scheme != "https" or host not in ALLOWED_HOSTS:
        raise DomainNotAllowed(f"{scheme}://{host} is not on the allowlist (pipeline/net/http.py)")
    return host


@dataclass
class RateLimiter:
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def wait(self, host: str) -> None:
        interval, key = ALLOWED_HOSTS[host], rate_key(host)
        with self._lock:
            now = self.clock()
            last = self._last.get(key)
            if last is not None and now - last < interval:
                self.sleep(interval - (now - last))
                now = self.clock()
            self._last[key] = now


@dataclass
class HttpClient:
    settings: Settings
    limiter: RateLimiter = field(default_factory=RateLimiter)
    mocks: dict[str, bytes] = field(default_factory=dict)
    mock_errors: dict[str, list[int]] = field(default_factory=dict)  # url -> HTTP statuses to raise first
    rate_limit_mocks: bool = False  # tests of the limiter itself (M3-06) turn this on, with a fake clock
    calls: list[str] = field(default_factory=list)  # URLs requested in mock mode, in order
    _client: httpx.Client | None = None

    def register_mock(self, url: str, body: bytes) -> None:
        self.mocks[url] = body

    def register_error(self, url: str, status: int, times: int = 1) -> None:
        """Mock mode: the next `times` requests for `url` fail with `status` (e.g. an NSE block is a 403)."""
        self.mock_errors.setdefault(url, []).extend([status] * times)

    def _headers(self, host: str) -> dict[str, str]:
        if host.endswith("sec.gov"):
            if not self.settings.sec_user_agent:
                raise RuntimeError("SEC_USER_AGENT is required for SEC requests (BRIEF §2.4)")
            return {"User-Agent": self.settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"}
        return dict(BROWSER_HEADERS)

    def _cache_path(self, url: str) -> Path:
        return self.settings.cache_dir / "http" / hashlib.sha256(url.encode()).hexdigest()

    def _mock(self, url: str, host: str) -> bytes:
        self.calls.append(url)
        if self.rate_limit_mocks:
            self.limiter.wait(host)
        errors = self.mock_errors.get(url)
        if errors:
            status = errors.pop(0)
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError(
                f"{status} (mock)", request=request, response=httpx.Response(status, request=request)
            )
        if url in self.mocks:
            return self.mocks[url]
        raise MockNotRegistered(url)

    def reset_session(self) -> None:
        """Drop the connection and its cookies (NSE: a forced re-warm rebuilds the session; DOOMBERG_AUDIT §4)."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def get_bytes(
        self, url: str, *, use_cache: bool = False, timeout: float = 60.0, headers: dict[str, str] | None = None
    ) -> bytes:
        host = check_allowed(url)
        if self.settings.mock_externals:
            return self._mock(url, host)
        cp = self._cache_path(url)
        if use_cache and cp.exists():
            return cp.read_bytes()
        self.limiter.wait(host)
        if self._client is None:
            self._client = httpx.Client(follow_redirects=False, timeout=timeout)
        r = self._client.get(url, headers={**self._headers(host), **(headers or {})})
        for _ in range(3):  # follow redirects only to allowlisted hosts
            if not (r.is_redirect and r.next_request is not None):
                break
            nxt = str(r.next_request.url)
            nhost = check_allowed(nxt)
            self.limiter.wait(nhost)
            r = self._client.get(nxt, headers={**self._headers(nhost), **(headers or {})})
        r.raise_for_status()
        body = r.content
        if use_cache:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_bytes(body)
        return body

    def download(self, url: str, dest: Path, *, timeout: float = 600.0) -> Path:
        """Stream a large file (SEC bulk zips are gigabytes) to `dest` without holding it in memory. Same allowlist,
        rate limit and mock rules as get_bytes; no redirects (bulk URLs are direct)."""
        host = check_allowed(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.settings.mock_externals:
            dest.write_bytes(self._mock(url, host))
            return dest
        self.limiter.wait(host)
        part = dest.with_name(dest.name + ".part")
        with httpx.stream("GET", url, headers=self._headers(host), timeout=timeout, follow_redirects=False) as r:
            r.raise_for_status()
            with part.open("wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
        part.replace(dest)
        return dest

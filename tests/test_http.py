"""pipeline/net/http.py: allowlist, rate limits, mock mode (BRIEF §2.3, §2.7; reviewer check 5c)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.net.http import ALLOWED_HOSTS, DomainNotAllowed, HttpClient, MockNotRegistered, RateLimiter, check_allowed
from pipeline.settings import Settings


def _settings(tmp_path: Path, mock: bool = True) -> Settings:
    return Settings(database_url="x", mock_externals=mock, sec_user_agent="test ua", cache_dir=tmp_path)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.anthropic.com/v1/messages",
        "https://api.openai.com/v1/chat/completions",
        "https://api.kite.trade/orders",
        "https://query1.finance.yahoo.com/v8/finance/chart/X",
        "http://www.sec.gov/files/company_tickers.json",  # plain http
        "https://www.sec.gov.evil.example/x",
    ],
)
def test_non_allowlisted_urls_raise(url: str, tmp_path: Path) -> None:
    with pytest.raises(DomainNotAllowed):
        HttpClient(_settings(tmp_path, mock=False)).get_bytes(url)


def test_allowlisted_host_passes_check() -> None:
    assert check_allowed("https://data.sec.gov/submissions/CIK0000320193.json") == "data.sec.gov"


def test_banned_paid_hosts_never_allowlisted() -> None:
    assert not {"api.anthropic.com", "api.openai.com"} & set(ALLOWED_HOSTS)


def test_mock_mode_serves_registered_and_refuses_the_rest(tmp_path: Path) -> None:
    c = HttpClient(_settings(tmp_path))
    c.register_mock("https://stooq.com/q/d/l/?s=aapl.us&i=w", b"Date,Close\n")
    assert c.get_bytes("https://stooq.com/q/d/l/?s=aapl.us&i=w") == b"Date,Close\n"
    with pytest.raises(MockNotRegistered):
        c.get_bytes("https://stooq.com/q/d/l/?s=msft.us&i=w")


def test_rate_limiter_spaces_requests_per_host() -> None:
    t = [0.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        t[0] += s

    rl = RateLimiter(clock=lambda: t[0], sleep=sleep)
    for _ in range(3):
        rl.wait("www.nseindia.com")
    assert slept == [3.0, 3.0]  # BRIEF §4.3: <= 1 request per 3 s
    rl.wait("stooq.com")  # a different host is not delayed by NSE
    assert slept == [3.0, 3.0]


def test_sec_requires_user_agent(tmp_path: Path) -> None:
    s = Settings(database_url="x", mock_externals=False, sec_user_agent=None, cache_dir=tmp_path)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        HttpClient(s)._headers("www.sec.gov")


def test_download_streams_in_mock_mode_and_checks_the_allowlist(tmp_path: Path) -> None:
    c = HttpClient(_settings(tmp_path))
    url = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
    c.register_mock(url, b"PK...")
    assert c.download(url, tmp_path / "bulk" / "submissions.zip").read_bytes() == b"PK..."
    with pytest.raises(MockNotRegistered):
        c.download("https://www.sec.gov/other.zip", tmp_path / "other.zip")
    with pytest.raises(DomainNotAllowed):
        HttpClient(_settings(tmp_path, mock=False)).download("https://example.com/x.zip", tmp_path / "x.zip")

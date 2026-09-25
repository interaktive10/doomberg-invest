"""NSE/BSE access rules (BRIEF §4.3, §8 M3-05, M3-06): 3 consecutive blocks -> stale -> BSE -> manual CSV import;
≤ 1 request per 3 s per NSE host; retries, re-warm and backoff; holidays don't count as blocks."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest

from pipeline.india import bhavcopy, manual_import
from pipeline.net.bse import BseClient
from pipeline.net.bse import bhavcopy_url as bse_url
from pipeline.net.http import HttpClient, RateLimiter
from pipeline.net.nse import NSE_HOME, NseBlocked, NseClient, NseStale
from pipeline.settings import Settings

FIN = Path(__file__).resolve().parents[2] / "fixtures" / "in"
DAY = date(2026, 6, 5)  # a Friday with real NSE and BSE files in F-IN
NSE_ZIP = (FIN / "bhavcopy" / "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip").read_bytes()
BSE_CSV = (FIN / "bhavcopy" / "BhavCopy_BSE_CM_0_0_0_20260605_F_0000.CSV").read_bytes()
BSE_HOME_PAGE = b"<!DOCTYPE html><html><head><title>BSE SENSEX</title></head></html>"  # BSE's missing-file answer


class Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def clients(tmp_path: Path, clock: Clock | None = None, limit: bool = False) -> tuple[HttpClient, NseClient, BseClient]:
    c = clock or Clock()
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path),
                      limiter=RateLimiter(clock=c, sleep=c.sleep), rate_limit_mocks=limit)  # fmt: skip
    return http, NseClient(http, clock=c, sleep=c.sleep), BseClient(http, sleep=c.sleep)


URL = bhavcopy.nse_url(DAY)


def test_three_403s_make_nse_stale(tmp_path: Path) -> None:
    http, nse, _ = clients(tmp_path)
    http.register_error(URL, 403, times=3)
    with pytest.raises(NseStale):
        nse.get(URL)
    assert nse.stale and nse.consecutive_blocks == 3
    assert http.calls == [NSE_HOME, URL, NSE_HOME, URL, URL]  # warm-up, block, rebuilt session + retry, backoff retry
    http.register_mock(URL, NSE_ZIP)
    with pytest.raises(NseStale):  # stale for the rest of the run: no more requests
        nse.get(URL)
    assert len(http.calls) == 5


def test_a_block_then_success_resets_the_count(tmp_path: Path) -> None:
    http, nse, _ = clients(tmp_path)
    http.register_error(URL, 403)
    http.register_mock(URL, NSE_ZIP)
    assert nse.get(URL) == NSE_ZIP and nse.consecutive_blocks == 0 and not nse.stale


def test_errors_that_are_not_blocks(tmp_path: Path) -> None:
    clock = Clock()
    http, nse, _ = clients(tmp_path, clock)
    http.register_error(URL, 404)
    with pytest.raises(httpx.HTTPStatusError):
        nse.get(URL)
    http.register_error(URL, 503, times=2)
    http.register_mock(URL, NSE_ZIP)
    assert nse.get(URL) == NSE_ZIP  # 5xx: exponential backoff, not a block
    assert clock.slept == [6.0, 12.0] and nse.consecutive_blocks == 0
    http.register_error(URL, 503, times=4)
    with pytest.raises(NseBlocked) as e:
        nse.get(URL)
    assert not isinstance(e.value, NseStale)


def test_nse_rate_is_one_request_per_3_seconds(tmp_path: Path) -> None:
    """M3-06: every request to an NSE host waits for 3 s after the previous one to that host."""
    clock = Clock()
    http, nse, _ = clients(tmp_path, clock, limit=True)
    urls = [bhavcopy.nse_url(date(2026, 6, d)) for d in (1, 2, 3, 4, 5)]
    for u in urls:
        http.register_mock(u, NSE_ZIP)
    times: dict[str, list[float]] = {}
    real_mock = http._mock

    def record(url: str, host: str) -> bytes:
        body = real_mock(url, host)
        times.setdefault(host, []).append(clock.t)
        return body

    http._mock = record  # type: ignore[method-assign]
    for u in urls:
        nse.get(u)
    arch = times["nsearchives.nseindia.com"]
    assert len(arch) == 5 and all(b - a >= 3.0 for a, b in zip(arch, arch[1:], strict=False))
    assert clock.t >= 12.0  # 5 archive requests need at least 4 gaps of 3 s


# ---------------------------------------------------------------- the weekly price chain


def test_nse_first(tmp_path: Path) -> None:
    http, nse, bse = clients(tmp_path)
    http.register_mock(bse_url(DAY), BSE_CSV)
    http.register_mock(URL, NSE_ZIP)
    rows, source, day, _ = bhavcopy.fetch_week(nse, bse, DAY, tmp_path / "imports")
    assert (source, day, len(rows)) == ("NSE", DAY, 2443)


def test_stale_nse_falls_back_to_bse(tmp_path: Path) -> None:
    """M3-05: 3 simulated 403s -> NSE stale -> the same day's BSE bhavcopy."""
    http, nse, bse = clients(tmp_path)
    http.register_mock(bse_url(DAY), BSE_CSV)
    http.register_error(URL, 403, times=3)
    rows, source, day, notes = bhavcopy.fetch_week(nse, bse, DAY, tmp_path / "imports")
    assert (source, day, len(rows), nse.stale) == ("BSE", DAY, 4823, True)
    assert notes == [f"NSE bhavcopy {DAY}: NseStale"]


def test_both_exchanges_down_uses_the_manual_import(tmp_path: Path) -> None:
    """M3-05: NSE stale and BSE failing -> the CSV Manzoor downloaded into imports/ produces the rows."""
    http, nse, bse = clients(tmp_path)
    http.register_error(bse_url(DAY), 503, times=3)
    http.register_error(URL, 403, times=3)
    imports = tmp_path / "imports"
    imports.mkdir()
    with zipfile.ZipFile(io.BytesIO(NSE_ZIP)) as z:
        (imports / "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv").write_bytes(z.read(z.namelist()[0]))
    (imports / "notes.csv").write_text("a,b\n1,2\n", encoding="utf-8")  # unrecognised: reported, skipped
    rows, source, day, _ = bhavcopy.fetch_week(nse, bse, DAY, imports)
    assert (source, day, len(rows)) == ("manual", DAY, 2443) and {r.series for r in rows} == {"EQ"}
    assert [i.kind for i in manual_import.import_dir(imports)] == ["bhavcopy", "unknown"]


def test_nothing_anywhere(tmp_path: Path) -> None:
    http, nse, bse = clients(tmp_path)
    http.register_error(bse_url(DAY), 503, times=3)
    http.register_error(URL, 403, times=3)
    assert bhavcopy.fetch_week(nse, bse, DAY, tmp_path / "none")[1:3] == ("none", None)


def test_a_holiday_walks_back_without_asking_nse(tmp_path: Path) -> None:
    http, nse, bse = clients(tmp_path)
    friday, thursday = date(2026, 6, 12), date(2026, 6, 11)
    http.register_mock(bse_url(friday), BSE_HOME_PAGE)  # no file: holiday
    http.register_mock(bse_url(thursday), BSE_CSV)
    http.register_mock(bhavcopy.nse_url(thursday), NSE_ZIP)
    rows, source, day, _ = bhavcopy.fetch_week(nse, bse, friday, tmp_path / "imports")
    assert (source, day) == ("NSE", thursday) and nse.consecutive_blocks == 0
    assert bhavcopy.nse_url(friday) not in http.calls


def test_bhavdata_full_manual_format(tmp_path: Path) -> None:
    text = ("SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, "
            "AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
            "KEI, EQ, 05-Jun-2026, 5296.45, 5301.05, 5398.00, 5290.00, 5336.00, 5335.50, 5345.2, 203971, 10902.3, "
            "20000, 100000, 49.03\n"
            "KEI, BE, 05-Jun-2026, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1\n")  # fmt: skip
    p = tmp_path / "sec_bhavdata_full_05062026.csv"
    p.write_text(text, encoding="utf-8")
    imp = manual_import.import_file(p)
    assert imp.kind == "bhavdata_full"
    assert [(r.symbol, r.close, r.volume, r.trade_date) for r in imp.prices] == [("KEI", 5335.50, 203971, DAY)]

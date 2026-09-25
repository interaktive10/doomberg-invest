"""EIA planned generator additions (BRIEF §2.7, §4.11): the request, paging, and the monthly MW sums."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from pipeline.capex import eia
from pipeline.net.http import HttpClient
from pipeline.settings import Settings

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "eia"


def test_the_request_asks_for_planned_units_monthly_with_the_key_as_a_parameter() -> None:
    q = parse_qs(urlsplit(eia.url("k3y", "2024-01", "2026-09", 5000)).query)
    assert q["api_key"] == ["k3y"] and q["frequency"] == ["monthly"] and q["data[0]"] == ["nameplate-capacity-mw"]
    assert q["facets[status][]"] == ["P", "L", "T", "U", "V", "TS"] and q["offset"] == ["5000"]
    assert (q["start"], q["end"]) == (["2024-01"], ["2026-09"])


def test_parse_sums_mw_per_month_end_and_skips_rows_without_capacity() -> None:
    got, total, n = eia.parse((FIX / "planned_page1.json").read_bytes())
    assert (total, n) == (5, 3) and got == {date(2026, 6, 30): D("370.5"), date(2026, 7, 31): D(1100)}
    with pytest.raises(eia.EiaError):
        eia.parse(b'{"error": "invalid api_key"}')


def test_pages_until_the_total_and_errors_never_show_the_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eia, "PAGE", 3)
    http = HttpClient(Settings(database_url="x", mock_externals=True, sec_user_agent="t", cache_dir=tmp_path))
    start, end = date(2026, 1, 1), date(2026, 9, 30)
    http.register_mock(eia.url("k3y", "2026-01", "2026-09", 0), (FIX / "planned_page1.json").read_bytes())
    http.register_mock(eia.url("k3y", "2026-01", "2026-09", 3), (FIX / "planned_page2.json").read_bytes())
    assert eia.planned_additions(http, "k3y", start, end) == [
        (date(2026, 6, 30), D("370.5")), (date(2026, 7, 31), D(1100)), (date(2026, 8, 31), D(1114))
    ]  # fmt: skip
    http.register_error(eia.url("s3cret", "2026-01", "2026-09", 0), 403)
    with pytest.raises(eia.EiaError) as e:
        eia.planned_additions(http, "s3cret", start, end)
    assert "s3cret" not in str(e.value) and "403" in str(e.value)

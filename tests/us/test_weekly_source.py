"""JsonSource over the bulk zips (review F1): the older-filings pages are indexed once, so a lookup doesn't scan the
~1M member names of submissions.zip per company."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

from pipeline.us.bulk import JsonSource


def test_pages_are_found_in_order(tmp_path: Path) -> None:
    z = tmp_path / "submissions.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for name in ("CIK0000000001.json", "CIK0000000001-submissions-002.json", "CIK0000000001-submissions-001.json",
                     "CIK0000000002.json", "CIK00000000010-submissions-001.json"):  # fmt: skip
            zf.writestr(name, b"{}")
    src = JsonSource(z)
    assert src.pages("0000000001") == [b"{}", b"{}"]
    assert src._pages["0000000001"] == ["CIK0000000001-submissions-001.json", "CIK0000000001-submissions-002.json"]
    assert src.pages("0000000002") == [] and src.read("CIK0000000002.json") == b"{}"


def test_lookup_cost_does_not_grow_with_the_member_count(tmp_path: Path) -> None:
    z = tmp_path / "big.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for i in range(40_000):
            zf.writestr(f"CIK{i:010d}.json", b"{}")
            zf.writestr(f"CIK{i:010d}-submissions-001.json", b"[]")
    src = JsonSource(z)
    t0 = time.monotonic()
    got = [src.pages(f"{i:010d}") for i in range(0, 40_000, 8)]
    elapsed = time.monotonic() - t0
    assert all(g == [b"[]"] for g in got)
    assert elapsed < 2.0  # 5,000 lookups among 80,000 members; the old per-call sort scaled with the member count

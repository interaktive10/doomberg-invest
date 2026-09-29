"""JsonSource over the bulk zips (review F1): the older-filings pages are indexed once, so a lookup doesn't scan the
~1M member names of submissions.zip per company."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

from pipeline.us.bulk import JsonSource, index_pages


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


def test_pages_index_answers_the_live_zip_in_seconds() -> None:
    """Review F1 acceptance: 6,047 lookups on a 1,000,000-member source in under 5 s, index build included (the live
    submissions.zip had 991,718 members; the old per-call sort took 0.69 s per company)."""
    names = [f"CIK{i:010d}.json" for i in range(600_000)]
    names += [f"CIK{i:010d}-submissions-{p:03d}.json" for i in range(200_000) for p in (2, 1)]
    t0 = time.monotonic()
    index = index_pages(names)
    got = [index.get(f"{i:010d}", []) for i in range(0, 6_047 * 50, 50)]
    elapsed = time.monotonic() - t0
    assert len(names) == 1_000_000 and elapsed < 5.0
    assert got[1] == ["CIK0000000050-submissions-001.json", "CIK0000000050-submissions-002.json"]
    assert got[-1] == []  # CIK 302,300 has no older pages

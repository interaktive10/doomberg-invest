#!/usr/bin/env python3
"""Read the web app's Playwright JSON report (web/e2e-report.json, written by `pnpm e2e`) for one M7 check.

`python3 scripts/e2e_report.py <spec file> [<spec file> ...]`: exit 0 when every test of those files passed (at least
one each), 1 when one failed or none ran, 2 when there is no report. Stdlib only, so the web CI job runs it without
the Python environment (scripts/verify.py M7-01..M7-03)."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPORT = Path(__file__).resolve().parent.parent / "web" / "e2e-report.json"


def specs(suite: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from suite.get("specs") or []
    for s in suite.get("suites") or []:
        yield from specs(s)


def main(argv: list[str]) -> int:
    if not REPORT.exists():
        print(f"no report at {REPORT} (run `pnpm e2e` in web/)")
        return 2
    doc = json.loads(REPORT.read_text(encoding="utf-8"))
    status = 0
    for name in argv:
        found = [s for top in doc.get("suites") or [] if str(top.get("file", "")).endswith(name) for s in specs(top)]
        ok = [s for s in found if s.get("ok") and all(t.get("status") in ("expected", "flaky") for t in s["tests"])]
        print(f"{name}: {len(ok)} of {len(found)} passed")
        for s in found:
            if s not in ok:
                print(f"  failed: {s.get('title')}")
        if not found or len(ok) != len(found):
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

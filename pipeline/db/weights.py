"""weights_versions provenance (BRIEF §3, §1.7, §4.8.7, §4.10.5): the version config/weights.yaml carries is recorded
and approved before a score names it. `python -m pipeline.db.weights` (weights.yml, on a push to main that changes
config/weights.yaml; the weekly scores run calls it too).

config/weights.yaml changes only through a PR with the human-approved label, so the version it carries on main is
approved. A version is immutable: a Lab proposal's row (its §4.10.5 reasons, approved_by null) is approved only when
the merged weights equal the proposed ones; an edited proposal must carry a new version (M8 review R2-F3).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import yaml

from pipeline.db import repo
from pipeline.db.models import WeightsVersion
from pipeline.settings import REPO_ROOT, Settings

INITIAL_VERSION = "w0-equal"
INITIAL_REASON = "initial weights from config/weights.yaml (BRIEF §1.7: equal; legacy L* at 0)"
MERGED_BY = "human-approved PR"
MERGED_REASON = "config/weights.yaml changed through a human-approved PR"


class WeightsMismatch(RuntimeError):
    """config/weights.yaml carries a version whose stored weights differ (an edited Lab proposal)."""


def read(root: Path = REPO_ROOT) -> dict[str, Any]:
    w: dict[str, Any] = yaml.safe_load((root / "config" / "weights.yaml").read_text(encoding="utf-8"))
    return w


def _norm(x: Any) -> Any:
    """Numbers as decimals (1, 1.0 and "1.0" alike), so YAML and the stored JSON compare by value."""
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_norm(v) for v in x]
    if isinstance(x, (int, float, Decimal)) and not isinstance(x, bool):
        return Decimal(str(x))
    return x


def _diff(a: Any, b: Any, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        return [d for k in sorted(a.keys() | b.keys()) for d in _diff(a.get(k), b.get(k), f"{path}.{k}".lstrip("."))]
    return [] if a == b else [f"{path}: stored {a} vs file {b}"]


def record_weights_in_use(conn: psycopg.Connection[Any], w: dict[str, Any]) -> bool:
    """Record (and approve) the version in config/weights.yaml. True when a row was inserted. The initial version is
    the brief's; any later one arrived through a human-approved PR: a Lab proposal already has its row, which is
    approved now if its weights are the merged ones; a version with no row gets one saying how it came in. Every
    approved row has approved_at. Raises WeightsMismatch when the stored weights of the version differ."""
    version = str(w["version"])
    weights = {k: v for k, v in w.items() if k != "version"}
    stored = repo.weights_version(conn, version)
    if stored is None:
        initial = version == INITIAL_VERSION
        return repo.insert_weights_version(
            conn,
            WeightsVersion(
                version=version,
                weights=weights,
                reason=INITIAL_REASON if initial else MERGED_REASON,
                approved_by="brief" if initial else MERGED_BY,
                approved_at=datetime.now(UTC),
            ),
        )
    diff = _diff(_norm(stored.weights), _norm(weights))
    if diff:
        raise WeightsMismatch(
            f"config/weights.yaml version {version!r} differs from the weights stored for that version "
            f"({'; '.join(diff[:5])}). A version is immutable: bump `version:` in config/weights.yaml (for example "
            f"{version}-edited) through a human-approved PR."
        )
    if stored.approved_by is None:
        repo.approve_weights_version(conn, version, MERGED_BY)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", default=None)
    a = ap.parse_args(argv)
    w = read()
    with psycopg.connect(a.database_url or Settings.from_env().database_url) as conn:
        try:
            inserted = record_weights_in_use(conn, w)
        except WeightsMismatch as e:
            print(f"weights: {e}", file=sys.stderr)
            return 1
    print(f"weights: version {w['version']} {'recorded' if inserted else 'already recorded'} and approved")
    return 0


if __name__ == "__main__":
    sys.exit(main())

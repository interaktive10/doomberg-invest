"""Evidence and Gap scores (BRIEF §1.7, §4.8). Evidence never uses price; Gap is the mean of the context scores.

Evidence:
- a family contributes min(1, sum of its top 2 weight x strength among fired signals);
- raw = sum over families of W_f x contribution; Evidence = 100 x min(1, raw / 2.0);
- fewer than 2 families contributing -> Evidence = min(Evidence, 55);
- each soft red flag subtracts 10, floored at 0.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from pipeline.settings import REPO_ROOT
from pipeline.signals.base import SignalResult
from pipeline.signals.series import ZERO

ONE_HUNDRED = Decimal(100)


def _d(x: object) -> Decimal:
    return Decimal(str(x))


@dataclass(frozen=True)
class Weights:
    version: str
    families: Mapping[str, Decimal]
    signals: Mapping[str, Decimal]
    context: Mapping[str, Decimal]

    @classmethod
    def load(cls, root: Path = REPO_ROOT) -> Weights:
        w: dict[str, Any] = yaml.safe_load((root / "config" / "weights.yaml").read_text(encoding="utf-8"))
        return cls(
            version=str(w["version"]),
            families={k: _d(v) for k, v in w["families"].items()},
            signals={k: _d(v) for k, v in w["signals"].items()},
            context={k: _d(v) for k, v in w["context"].items()},
        )


@dataclass(frozen=True)
class Evidence:
    score: Decimal
    raw: Decimal
    contributions: Mapping[str, Decimal]
    families: tuple[str, ...]  # families that contributed
    soft_flags: int
    capped: bool  # the 2-family cap applied


def evidence(
    results: Mapping[str, SignalResult], soft_flags: int, weights: Weights, cfg: Mapping[str, Any]
) -> Evidence:
    """cfg is config/signals.yaml `scores`. Only its families and their signals are read, so a weight with no family
    there (S11's and the capex family's, left in config/weights.yaml: SPEC_ISSUES 52) counts for nothing."""
    top = int(cfg["max_signals_per_family"])
    contrib: dict[str, Decimal] = {}
    for family, ids in cfg["families"].items():
        parts = sorted(
            (
                weights.signals.get(s, Decimal(1)) * results[s].strength
                for s in ids
                if s in results and results[s].fired
            ),
            reverse=True,
        )
        contrib[family] = min(Decimal(1), sum(parts[:top], ZERO))
    raw = sum((weights.families.get(f, Decimal(1)) * v for f, v in contrib.items()), ZERO)
    score = ONE_HUNDRED * min(Decimal(1), raw / _d(cfg["evidence_divisor"]))
    families = tuple(f for f, v in contrib.items() if v > 0)
    capped = len(families) < int(cfg["min_families"]) and score > _d(cfg["single_family_cap"])
    if len(families) < int(cfg["min_families"]):
        score = min(score, _d(cfg["single_family_cap"]))
    score = max(ZERO, score - _d(cfg["soft_flag_penalty"]) * soft_flags)
    return Evidence(score, raw, contrib, families, soft_flags, capped)


def gap(context_scores: Mapping[str, Decimal | None], weights: Weights, min_metrics: int) -> Decimal | None:
    """The (weighted, equal by default) mean of the available C1-C3 scores; None with fewer than min_metrics. Only the
    given metrics' weights are read, so a weight with no metric (C4's, left in config/weights.yaml: SPEC_ISSUES 48)
    counts for nothing."""
    known = {k: v for k, v in context_scores.items() if v is not None}
    if len(known) < min_metrics:
        return None
    w = {k: weights.context.get(k, Decimal(1)) for k in known}
    total = sum(w.values(), ZERO)
    if total == 0:
        return None
    return sum((w[k] * v for k, v in known.items()), ZERO) / total

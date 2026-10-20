"""F-SYN evaluation (BRIEF §9, M5-01): run the planted-fact corpus through the engine and score it.

- recall: planted facts found with the expected Verify-1 status (verified, or needs_review for the non-USD one);
- precision: stored facts (verified or needs_review) that are planted facts.
A stored fact matches a planted one of the same document and type when the values agree within 0.5% (for a fact
with numbers), or when one quote contains the other (for a fact without numbers).

`python -m pipeline.facts.evaluate --replay` scores the committed cassettes (M5-01: recall >= 95%, precision >=
98%; exit 1 below). `--record` runs the real free-tier providers and records cassettes (record-cassettes.yml): F-SYN's
P-01 corpus and the P-02 and P-07 samples (pipeline.facts.samples); both modes run the samples too.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pipeline.facts.ground import ground
from pipeline.facts.process import DocMeta, Outcome, extract_document, normalize
from pipeline.facts.verify1 import Candidate
from pipeline.llm.router import Router
from pipeline.settings import REPO_ROOT

SYN = REPO_ROOT / "fixtures" / "syn"
MIN_RECALL, MIN_PRECISION = 0.95, 0.98
VALUE_TOL = Decimal("0.005")


def load_truth(root: Path = SYN) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((root / "ground_truth.json").read_text(encoding="utf-8"))
    return doc


def meta_of(truth: Mapping[str, Any], d: Mapping[str, Any]) -> DocMeta:
    c = truth["companies"][d["ticker"]]
    return DocMeta(c["name"], d["ticker"], c["fye"], d["kind"], d["title"], datetime.fromisoformat(d["published_at"]))


def run_corpus(router: Router, root: Path = SYN, truth: Mapping[str, Any] | None = None) -> dict[str, Outcome]:
    truth = truth or load_truth(root)
    out = {}
    for d in truth["documents"]:
        body = (root / d["file"]).read_bytes()
        out[d["file"]] = extract_document(meta_of(truth, d), normalize(d["file"], body), router)
    return out


def _close(a: Decimal | None, planted: str | None) -> bool:
    if planted is None:
        return True
    if a is None:
        return False
    p = Decimal(planted)
    return abs(a - p) <= VALUE_TOL * abs(p) if p != 0 else a == 0


def _quotes_overlap(a: str, b: str) -> bool:
    return ground(a, b) is not None or ground(b, a) is not None


def matches(c: Candidate, p: Mapping[str, Any]) -> bool:
    if c.fact_type != p["fact_type"]:
        return False
    if p.get("value") is None and p.get("low") is None and p.get("high") is None:
        return _quotes_overlap(c.quote, p["quote"])
    if p.get("low") is not None or p.get("high") is not None:
        return _close(c.value_low, p.get("low")) and _close(c.value_high, p.get("high"))
    return _close(c.value_num, p.get("value"))


@dataclass
class Report:
    planted: int = 0
    recalled: int = 0
    stored: int = 0
    correct: int = 0
    misses: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return self.recalled / self.planted if self.planted else 1.0

    @property
    def precision(self) -> float:
        return self.correct / self.stored if self.stored else 1.0

    def summary(self) -> str:
        return (f"F-SYN: recall {self.recall:.1%} ({self.recalled}/{self.planted}), precision {self.precision:.1%} "
                f"({self.correct}/{self.stored}); deferred documents: {len(self.deferred)}")  # fmt: skip


def score(outcomes: Mapping[str, Outcome], truth: Mapping[str, Any]) -> Report:
    r = Report()
    for d in truth["documents"]:
        o = outcomes.get(d["file"])
        stored = [c for c, _ in o.facts] if o is not None else []
        if o is not None and o.status == "deferred":
            r.deferred.append(d["file"])
        used: set[int] = set()
        for p in d["facts"]:
            r.planted += 1
            hit = next((i for i, c in enumerate(stored) if i not in used and matches(c, p)), None)
            if hit is not None and stored[hit].verification_status == p["status"]:
                used.add(hit)
                r.recalled += 1
            else:
                got = "not found" if hit is None else f"status {stored[hit].verification_status}"
                r.misses.append(f"{d['file']}: {p['fact_type']} {p['subject_key']} ({got})")
        r.stored += len(stored)
        for i, c in enumerate(stored):
            if any(matches(c, p) for p in d["facts"]):
                r.correct += 1
            elif i not in used:
                r.extras.append(f"{d['file']}: {c.fact_type} {c.subject_key} {c.value_num} ({c.verification_status})")
    return r


def main(argv: Sequence[str] | None = None) -> int:
    from pipeline.llm import cassettes
    from pipeline.llm.quotas import Quotas

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replay", action="store_true", help="score the committed cassettes (M5-01)")
    mode.add_argument("--record", action="store_true", help="call the free-tier providers and record cassettes")
    a = ap.parse_args(argv)
    quotas = Quotas.load()
    if a.replay:
        if cassettes.recorded(prompt_id="P-01") == 0:
            print("F-SYN: no P-01 cassettes recorded yet (record-cassettes.yml with the free keys)")
            return 2
        problems = cassettes.manifest_problems()
        if problems:
            print("cassettes don't match MANIFEST.sha256:\n" + "\n".join(problems))
            return 1
        names = list(quotas.providers)
        unlimited = {n: {**quotas.raw["providers"][n], "requests_per_day": 10**9} for n in names}
        replay = Quotas.from_doc({**quotas.raw, "providers": unlimited})
        router = Router({n: cassettes.Player(n) for n in names}, replay)
    else:
        from pipeline.llm.clients import providers
        from pipeline.net.http import HttpClient
        from pipeline.settings import Settings

        settings = Settings.from_env()
        live = providers(HttpClient(settings), settings, quotas)
        router = Router({n: cassettes.Recorder(p) for n, p in live.items()}, quotas)
    truth = load_truth()
    report = score(run_corpus(router, truth=truth), truth)
    from pipeline.facts.samples import run_samples  # P-02, P-07 (M5 review R1-F7)
    from pipeline.llm.router import Done

    samples = run_samples(router, SYN, truth)
    if a.record:
        cassettes.write_manifest()
    print(report.summary())
    print("samples: " + ", ".join(f"{pid} {sum(isinstance(r, Done) for r in rs)}/{len(rs)}"
                                  for pid, rs in samples.items()))  # fmt: skip
    for line in report.misses + [f"extra: {e}" for e in report.extras]:
        print(f"  {line}")
    return 0 if report.recall >= MIN_RECALL and report.precision >= MIN_PRECISION and not report.deferred else 1


if __name__ == "__main__":
    sys.exit(main())

"""The other prompts' samples for record-cassettes.yml (BRIEF §9 "P-01, P-02, P-05, P-06, P-07 ..."; M5 review
R1-F7). Besides F-SYN's P-01 corpus (evaluate.run_corpus): one P-02 batch (F-SYN's counterparties against its
companies), one P-06 profile (ARVL's order announcement) and P-07 triage of F-SYN's India press releases. They run
from files alone, with the inputs the pipeline builds (run.link_pending, capex.run.cross_border,
run.triage_announcements), so `evaluate --record` writes cassettes under each prompt and `--replay` reads them back.
P-03 is no longer called (docs/SPEC_ISSUES.md 50); F-SYN keeps KYST's two risk-factor versions.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from pipeline.capex.membership import MAX_TEXT_CHARS, CrossBorderInput
from pipeline.facts import entities
from pipeline.facts.process import normalize
from pipeline.india.triage import SUMMARY_CHARS, TriageInput
from pipeline.llm.prompt import PromptInput
from pipeline.llm.router import Deferred, Done, Router
from pipeline.settings import REPO_ROOT

LINK_BATCH = 20  # pipeline.facts.run.LINK_BATCH


def inputs(root: Path, truth: Mapping[str, Any], config_root: Path = REPO_ROOT) -> dict[str, list[PromptInput]]:
    """prompt id -> the sample inputs."""
    names = sorted({str(f["counterparty"]) for d in truth["documents"] for f in d["facts"] if f.get("counterparty")})
    pool = [entities.Candidate(f"c:{t}", str(c["name"])) for t, c in sorted(truth["companies"].items())]
    batch = names[:LINK_BATCH]
    cands = tuple(dict.fromkeys((c.id, c.name) for n in batch for c in entities.candidates_for(n, pool)))
    out: dict[str, list[PromptInput]] = {"P-02": [entities.EntityInput(tuple(batch), cands)]}

    cats = tuple(yaml.safe_load((config_root / "config" / "categories.yaml").read_text(encoding="utf-8"))["categories"])
    india = [d for d in truth["documents"] if truth["companies"][d["ticker"]]["market"] == "in"]
    out["P-06"], out["P-07"] = [], []
    for d in india:
        c = truth["companies"][d["ticker"]]
        text = normalize(d["file"], (root / d["file"]).read_bytes()).text
        out["P-06"].append(CrossBorderInput(str(c["name"]), str(d["ticker"]), cats, text[:MAX_TEXT_CHARS]))
        out["P-07"].append(TriageInput(str(d["title"]), text[:SUMMARY_CHARS]))
    return out


def run_samples(router: Router, root: Path, truth: Mapping[str, Any]) -> dict[str, list[Done | Deferred]]:
    return {pid: [router.call(i) for i in items] for pid, items in inputs(root, truth).items()}

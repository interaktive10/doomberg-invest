"""The other prompts' samples for record-cassettes.yml (BRIEF §9 "P-01, P-02, P-03, P-05, P-06, P-07 ..."; M5 review
R1-F7). Besides F-SYN's P-01 corpus (evaluate.run_corpus): one P-02 batch (F-SYN's counterparties against its
companies), P-03 tags for KYST's risk-factor changes, one P-06 profile (ARVL's order announcement) and P-07 triage
of F-SYN's India press releases. They run from files alone, with the inputs the pipeline builds (run.link_pending,
run.risk_changes, capex.run.cross_border, run.triage_announcements), so `evaluate --record` writes cassettes under
each prompt and `--replay` reads them back.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from pipeline.capex.membership import MAX_TEXT_CHARS, CrossBorderInput
from pipeline.facts import entities, risk_diff
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

    rc = truth["risk_changes"]
    old, new = (normalize(rc[k], (root / rc[k]).read_bytes()) for k in ("from", "to"))
    spans = [next(s for s in n.section_map if s["name"] == "risk_factors") for n in (old, new)]
    old_p, new_p = (risk_diff.paragraphs(n.text, int(str(s["char_start"])), int(str(s["char_end"])))
                    for n, s in zip((old, new), spans, strict=True))  # fmt: skip
    changes = risk_diff.compare(old_p, new_p)
    out["P-03"] = [risk_diff.RiskTagInput(tuple((f"p{k}", p.text[:2000]) for k, c in enumerate(changes)
                                                if (p := c.new or c.old) is not None))]  # fmt: skip

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

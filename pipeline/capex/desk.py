"""The Capex Desk's shared pieces (BRIEF §4.11): the category config, the anchor companies, and S11's CapexView per
company for the weekly scoring run (confirmed memberships only, the latest demand index, graph distance, export
exposure). Kept apart from run.py so the scoring run doesn't import the text-facts machinery."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import yaml

from pipeline.capex import graph
from pipeline.capex.view import export_signals, view
from pipeline.db import facts_repo
from pipeline.db.models import Company
from pipeline.db.pit import as_of, cutoff_for
from pipeline.settings import REPO_ROOT
from pipeline.signals.base import CapexView


def config(root: Path = REPO_ROOT) -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load((root / "config" / "categories.yaml").read_text(encoding="utf-8"))
    return cfg


def anchors(companies: Sequence[Company], cfg: Mapping[str, Any]) -> dict[UUID, str]:
    wanted = {str(t).upper() for t in cfg["anchors"]}
    return {c.id: str(c.ticker).upper() for c in companies
            if c.id is not None and c.market == "us" and (c.ticker or "").upper() in wanted}  # fmt: skip


def load_views(conn: psycopg.Connection[Any], week: date, companies: Sequence[Company],
               cfg: Mapping[str, Any] | None = None) -> dict[UUID, CapexView]:  # fmt: skip
    """CapexView for every company with a confirmed membership (the rest get S11's empty view)."""
    cfg = cfg or config()
    confirmed: dict[UUID, list[str]] = defaultdict(list)
    for m in facts_repo.memberships(conn, "confirmed"):
        confirmed[m["company_id"]].append(m["category"])
    if not confirmed:
        return {}
    index = {r["category"]: (r["direction"], r["input_growth"]) for r in facts_repo.capex_index(conn, week)}
    names = {c.id: (c.name, c.cik) for c in companies if c.id is not None}
    links = [graph.LinkRow(r["from_company_id"], r["to_entity_id"], r["entity_name"], r["entity_cik"])
             for r in facts_repo.links(conn) if r["first_seen_at"] < cutoff_for(week)]  # fmt: skip
    dist = graph.distances(links, names, anchors(companies, cfg))
    ids = list(confirmed)
    facts: dict[UUID, list[Any]] = defaultdict(list)
    for f in as_of(week).facts(conn, ids):
        facts[f.company_id].append(f)
    quotes = facts_repo.export_quotes(conn, ids, cutoff_for(week))
    out = {}
    for cid, cats in confirmed.items():
        rising, quote_ok = export_signals(facts.get(cid, []), quotes.get(cid, {}))
        out[cid] = view(cats, index, dist.get(cid), rising, quote_ok)
    return out

"""The counterparty graph's distance from the anchors (BRIEF §4.11; S11's "second-order: graph distance 2").

Nodes are companies and entities; an edge joins a company to each entity it links to (links, from verified facts),
and an entity to the company it is (same CIK, or the same normalized name). The anchors (config/categories.yaml,
hyperscalers) are distance 0; a company one link away from an anchor, in either direction, is 1; its own
counterparties are 2. Breadth-first over companies only (entities are the hinges between them).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from uuid import UUID

from pipeline.facts.entities import normalize_name


@dataclass(frozen=True)
class LinkRow:
    from_company_id: UUID
    to_entity_id: UUID
    entity_name: str
    entity_cik: str | None


def entity_companies(links: Iterable[LinkRow], companies: Mapping[UUID, tuple[str, str | None]]) -> dict[UUID, UUID]:
    """entity id -> the company it is, by CIK first, else by normalized name. `companies`: id -> (name, cik)."""
    by_cik = {cik.lstrip("0"): cid for cid, (_, cik) in companies.items() if cik}
    by_name = {normalize_name(name): cid for cid, (name, _) in companies.items()}
    out = {}
    for link in links:
        cid = (by_cik.get((link.entity_cik or "").lstrip("0")) if link.entity_cik else None) or by_name.get(
            normalize_name(link.entity_name)
        )
        if cid is not None:
            out[link.to_entity_id] = cid
    return out


def distances(
    links: Iterable[LinkRow], companies: Mapping[UUID, tuple[str, str | None]], anchors: Iterable[UUID]
) -> dict[UUID, int]:
    links = list(links)
    ent = entity_companies(links, companies)
    adj: dict[UUID, set[UUID]] = defaultdict(set)
    for link in links:
        other = ent.get(link.to_entity_id)
        if other is not None and other != link.from_company_id:
            adj[link.from_company_id].add(other)
            adj[other].add(link.from_company_id)
    dist = {a: 0 for a in anchors}
    queue = deque(dist)
    while queue:
        c = queue.popleft()
        for n in adj[c]:
            if n not in dist:
                dist[n] = dist[c] + 1
                queue.append(n)
    return dist

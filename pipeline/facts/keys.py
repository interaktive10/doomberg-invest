"""subject_key validation (Appendix F.4 step 7): P-01 proposes a key from config/subject_keys.yaml and code checks it
against the vocabulary and the fact type's prefix (types.KEY_PREFIX). A `<slot>` is a lower-case slug. Keys that
don't fit become `other:<slug>` and the fact goes to needs_review. A vocabulary key the model garbled at its end
("lease_not_commenced:total,unit:", "purchase_obligations:totalkoh": docs/SPEC_ISSUES.md 59) is repaired first."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import yaml

from pipeline.facts.types import KEY_PREFIX
from pipeline.settings import REPO_ROOT

SLOT = r"[A-Za-z0-9](?:[A-Za-z0-9_.\-]*[A-Za-z0-9])?"


@cache
def vocabulary(root: Path = REPO_ROOT) -> tuple[list[str], tuple[re.Pattern[str], ...], str]:
    doc = yaml.safe_load((root / "config" / "subject_keys.yaml").read_text(encoding="utf-8"))
    keys = [str(k) for k in doc["keys"]]
    pats = tuple(re.compile("^" + re.sub(r"<[^>]+>", SLOT, re.escape(k).replace(r"\<", "<").replace(r"\>", ">")) + "$")
                 for k in keys)  # fmt: skip
    return keys, pats, str(doc.get("other_prefix", "other:"))


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:60].strip("_") or "unnamed"


def normalize(key: str) -> str:
    k = key.strip().lower()
    k = re.sub(r"\s+", "_", k)
    return re.sub(r"_*:_*", ":", k)


def valid(fact_type: str, key: str) -> bool:
    _, pats, _ = vocabulary()
    return key.startswith(KEY_PREFIX.get(fact_type, ("\0",))) and any(p.match(key) for p in pats)


PERIOD_KEYED = frozenset({"capex_guidance", "capex_reported"})
_KEY_CHARS = re.compile(r"[a-z0-9_.:\-]+")


def repaired(fact_type: str, key: str) -> str | None:
    """A valid key for a garbled one: the key cut at its first character no key has (",unit:" leaked from the next
    field), else the longest slot-free vocabulary key of the type it starts with ("purchase_obligations:totalkoh");
    None when neither fits. Only for a key that isn't valid as it stands."""
    m = _KEY_CHARS.match(key)
    cut = m.group(0).rstrip(":_.-") if m else ""
    if cut and cut != key and valid(fact_type, cut):
        return cut
    keys, _, _ = vocabulary()
    prefixes = KEY_PREFIX.get(fact_type, ("\0",))
    fixed = [k for k in keys if "<" not in k and k.startswith(prefixes) and key.startswith(k)]
    return max(fixed, key=len) if fixed else None


def check(fact_type: str, proposed: str | None, subject: str, period: str | None = None) -> tuple[str, bool]:
    """(the key to store, whether it is a valid vocabulary key). Capex guidance/reported keys are built by code from
    the resolved period (`capex_guidance:FY2027`, `capex_reported:Q2FY2026`), so the same period always gets the same
    key; any other invalid key becomes other:<slug>."""
    _, _, other = vocabulary()
    if fact_type in PERIOD_KEYED and period:
        return f"{KEY_PREFIX[fact_type][0]}{period}", True
    key = normalize(proposed or "")
    if key and valid(fact_type, key):
        return key, True
    fixed = repaired(fact_type, key) if key else None
    if fixed is not None:
        return fixed, True
    if key.startswith(other) and re.fullmatch(SLOT, key[len(other) :]):
        return key, False
    return f"{other}{slug(key.split(':', 1)[-1] if key else subject)}", False

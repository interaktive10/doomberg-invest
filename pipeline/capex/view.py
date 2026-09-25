"""S11's view of the Capex Desk per company (pipeline.signals.base.CapexView, BRIEF §4.11):

- categories: the company's confirmed memberships only (M5-06);
- direction and input growth of each category: the latest demand index on or before the week;
- graph distance from an anchor (graph.py);
- export exposure: rising when the company's two latest verified export_exposure share facts rise (or it has an
  overseas order book fact newer than a year); export_quote when a verified export fact's quote names the US or data
  centers (the India bonus).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from uuid import UUID

from pipeline.capex.inputs import FactLike
from pipeline.signals.base import CapexView

US_OR_DATA_CENTER = re.compile(r"\b(?:U\.?S\.?A?|United States|America|data[- ]cent(?:er|re)s?|hyperscal\w*)\b", re.I)


def export_signals(facts: Sequence[FactLike], quotes: Mapping[UUID, str] | None = None) -> tuple[bool, bool]:
    """(export exposure rising, a verified export quote naming the US or data centers) from a company's facts."""
    exp = sorted((f for f in facts if f.fact_type == "export_exposure"), key=lambda f: (f.as_of, f.published_at))
    shares = [f.value_num for f in exp if f.subject_key == "export_exposure:share_pct" and f.value_num is not None]
    rising = len(shares) >= 2 and shares[-1] > shares[-2]
    books = [f for f in exp if f.subject_key == "export_exposure:overseas_order_book"]
    if books and len(books) >= 2:
        a, b = books[-2].value_num, books[-1].value_num
        rising = rising or (a is not None and b is not None and b > a)
    quote_ok = any(US_OR_DATA_CENTER.search(q) for q in (quotes or {}).values())
    return rising, quote_ok


def view(
    confirmed: Sequence[str],
    index: Mapping[str, tuple[str, Decimal | None]],
    distance: int | None,
    export_rising: bool,
    export_quote: bool,
) -> CapexView:
    """`index`: category -> (direction, input growth)."""
    return CapexView(
        categories=tuple(sorted(confirmed)),
        direction={c: index[c][0] for c in confirmed if c in index},
        input_growth={c: g for c in confirmed if c in index and (g := index[c][1]) is not None},
        graph_distance=distance,
        export_exposure_rising=export_rising,
        export_quote=export_quote,
    )

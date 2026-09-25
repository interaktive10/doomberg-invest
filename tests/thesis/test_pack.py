"""M6-01 (pure parts): the pack schema, stable ids, public data only; the next filing window; kill-metric values."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal as D
from pathlib import Path

from pipeline.db.models import OwnershipRow
from pipeline.llm import privacy
from pipeline.signals.series import Quarter, Series
from pipeline.thesis import evidence_pack as ep

F = Path(__file__).resolve().parents[2] / "fixtures" / "card"
PACK = json.loads((F / "pack.json").read_text(encoding="utf-8"))
PRIVATE = re.compile(r"journal|post_?mortem|portfolio|position|reason", re.I)


def test_f_card_pack_matches_the_schema_and_its_ids_are_unique_and_well_formed() -> None:
    pack = ep.EvidencePack.model_validate(PACK)
    ids = pack.ids()
    assert len(ids) == len(set(ids)) and all(ep.ID.match(i) for i in ids)
    assert ep.to_json(pack) == json.loads(json.dumps(ep.to_json(ep.EvidencePack.model_validate(ep.to_json(pack)))))


def test_the_schema_has_no_private_field() -> None:
    """Only the declared fields exist (extra fields are refused), and none of them is a private one."""
    names: list[str] = []
    for model in (ep.EvidencePack, ep.Identifiers, ep.Metric, ep.SignalItem, ep.ContextItem, ep.FactItem,
                  ep.InsiderItem, ep.LinkItem, ep.KillMetric, ep.FilingWindow):  # fmt: skip
        names += list(model.model_fields)
    assert not [n for n in names if PRIVATE.search(n)]
    bad = {**PACK, "portfolio_pct": 5}
    try:
        ep.EvidencePack.model_validate(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("an extra field was accepted")


def test_router_inputs_built_from_a_pack_are_public_data() -> None:
    privacy.check(ep.CardInput(json.dumps(PACK)))
    privacy.check(ep.ClaimInput("Revenue rose.", ("quote",), ("m:x = 1",)))


def test_next_filing_windows() -> None:
    w = ep.next_filing("us", "0630", date(2026, 6, 30), date(2026, 9, 18))
    assert w is not None and (w.period_end, w.form, w.closes) == (date(2026, 9, 30), "10-Q", date(2026, 11, 14))
    w = ep.next_filing("us", "1231", date(2026, 9, 30), date(2026, 11, 20))
    assert w is not None and (w.form, w.closes) == ("10-K", date(2027, 3, 31))
    w = ep.next_filing("in", None, date(2025, 12, 31), date(2026, 3, 20))
    assert w is not None and (w.form, w.closes) == ("annual results", date(2026, 5, 30))
    late = ep.next_filing("us", "1231", date(2025, 12, 31), date(2026, 9, 18))  # two quarters not yet in the data
    assert late is not None and late.period_end == date(2026, 9, 30)
    assert ep.next_filing("us", "1231", None, date(2026, 9, 18)) is None


def test_kill_values_use_the_signal_code() -> None:
    ends = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31),
            date(2026, 6, 30), date(2026, 9, 30), date(2026, 12, 31)]  # fmt: skip
    rows = [Quarter(e, {"revenue": D(100 + 10 * i), "op_income": D(20)}) for i, e in enumerate(ends)]
    k = ep.KillInputs(Series(rows, "us"), [OwnershipRow(company_id="00000000-0000-4000-8000-000000000001",
                      quarter_end=date(2026, 12, 31), filed_at="2027-02-14T00:00:00Z", inst_holders=300,
                      source="sec_13f")], {"S1": D("0.8")}, D(55))  # fmt: skip
    assert ep.kill_value("revenue_ttm", k) == D(140 + 150 + 160 + 170)
    assert ep.kill_value("revenue_ttm_yoy", k) == D(620) / D(100 + 110 + 120 + 130) - 1
    assert ep.kill_value("inst_holders", k) == D(300) and ep.kill_value("evidence", k) == D(55)
    assert ep.kill_value("signal:S1", k) == D("0.8") and ep.kill_value("signal:S9", k) == D(0)
    assert ep.is_kill_metric("m:roic") and ep.is_kill_metric("m:signal:S12") and not ep.is_kill_metric("m:revenue")


def test_company_keys_and_week_labels() -> None:
    from pipeline.db.models import Company

    assert ep.company_key(Company(market="us", name="Brown-Forman", ticker="BF.B")) == "us-bf.b"
    assert ep.company_key(Company(market="in", name="M&M", nse_symbol="M&M")) == "in-m-m"
    assert ep.week_label(date(2026, 9, 18)) == "2026-W38" and ep.week_label(date(2027, 1, 1)) == "2026-W53"

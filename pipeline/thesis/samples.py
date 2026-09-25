"""P-04 and P-05 samples for record-cassettes.yml (BRIEF §9: "... P-05, ... and fallback P-04"; M6 review R1-F13).

P-04 writes a card for F-CARD's pack (fixtures/card/pack.json), and validate.py sends each of its fact and
why-mispriced items to P-05 (M6 review R3-F1). `python -m pipeline.thesis.samples --record` calls the free-tier
providers through cassette recorders; `--replay` runs the same on the committed cassettes and exits 2 while no P-04
cassette is recorded (verify M6-04: BLOCKED(key) until then), 1 when the replayed card fails validation.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.llm.router import Deferred, Done, Router
from pipeline.settings import REPO_ROOT
from pipeline.thesis import validate as v
from pipeline.thesis.evidence_pack import CardInput, EvidencePack

PACK = REPO_ROOT / "fixtures" / "card" / "pack.json"


def run(router: Router, pack_path: Path = PACK) -> tuple[Done | Deferred, v.Result | None]:
    """P-04 on the pack, then the card through validate.py (its P-05 calls go through the same router)."""
    doc: dict[str, Any] = json.loads(pack_path.read_text(encoding="utf-8"))
    answer = router.call(CardInput(EvidencePack.model_validate(doc)))
    if isinstance(answer, Deferred):
        return answer, None
    return answer, v.validate(answer.content, doc, v.hype_words(), router)


def main(argv: Sequence[str] | None = None) -> int:
    from pipeline.llm import cassettes
    from pipeline.llm.quotas import Quotas

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--replay", action="store_true")
    a = ap.parse_args(argv)
    quotas = Quotas.load()
    if a.replay:
        if cassettes.recorded(prompt_id="P-04") == 0:
            print("thesis samples: no P-04 cassette recorded yet (record-cassettes.yml with the free keys)")
            return 2
        names = list(quotas.providers)
        unlimited = {n: {**quotas.raw["providers"][n], "requests_per_day": 10**9} for n in names}
        router = Router(
            {n: cassettes.Player(n) for n in names}, Quotas.from_doc({**quotas.raw, "providers": unlimited})
        )
    else:
        from pipeline.llm.clients import providers
        from pipeline.net.http import HttpClient
        from pipeline.settings import Settings

        settings = Settings.from_env()
        live = providers(HttpClient(settings), settings, quotas)
        router = Router({n: cassettes.Recorder(p) for n, p in live.items()}, quotas)
    answer, result = run(router)
    if a.record:
        cassettes.write_manifest()
    if result is None:
        print(f"thesis samples: P-04 deferred ({answer.reason if isinstance(answer, Deferred) else ''})")
        return 1
    print(f"thesis samples: P-04 card {'passes' if result.ok else 'fails'} validation")
    for e in result.errors:
        print(f"  {e}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())

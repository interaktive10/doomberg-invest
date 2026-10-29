"""The thesis vault (BRIEF §4.9, §2.4; docs/SPEC_ISSUES.md 60). The repository is public, and the thesis queue holds
Manzoor's research entries while the cards say what he is researching, so git holds them only sealed: Fernet
(AES-128-CBC with HMAC-SHA256, `cryptography`) under a key derived with scrypt from THESIS_VAULT_KEY, which is a GitHub
secret and an environment variable of the routine's environment (Appendix G).

- `data/thesis_queue/<week>.sealed`: the week's queue document (weekly.yml seals and commits it).
- `data/thesis_cards/<week>.sealed`: the week's card files, one bundle (each card's .json and .md, and FAILED.md); the
  routine seals and pushes it. One file per card would name the company in its path.

validate.py, render.py, ingest.py and the fallback read the plaintext working copies (`data/thesis_queue/<week>.json`
and `data/thesis_cards/<week>/`), which .gitignore keeps out of git. A sealed file whose content is unchanged is left
as it is, so sealing a week again commits nothing new. A wrong key or a changed byte fails with VaultError; nothing is
written then.

`python -m pipeline.thesis.vault open [--week W]` (default: the newest sealed queue) writes the week's working copies;
`python -m pipeline.thesis.vault seal --week W` seals the week's cards, `--queue` its queue."""

from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from pipeline.settings import REPO_ROOT, Settings
from pipeline.thesis.validate import cards_dir, queue_path

SALT = b"doomberg-thesis-vault"
MIN_SECRET = 24  # characters: a generated secret (Appendix G), not a password
WEEK = re.compile(r"^\d{4}-W\d{2}$")
CARD_FILE = re.compile(r"^(?:[a-z0-9][a-z0-9._-]*\.(?:json|md)|FAILED\.md)$")


class VaultError(Exception):
    """A missing or short key, a wrong key, a changed file, or a bundle that isn't the week's cards."""


@functools.lru_cache(maxsize=4)
def fernet(secret: str) -> Fernet:
    if len(secret.strip()) < MIN_SECRET:
        raise VaultError(f"THESIS_VAULT_KEY must be at least {MIN_SECRET} characters (Appendix G: a generated one)")
    key = hashlib.scrypt(secret.strip().encode(), salt=SALT, n=2**15, r=8, p=1, maxmem=2**26, dklen=32)
    return Fernet(base64.urlsafe_b64encode(key))


def secret_from_env() -> str | None:
    return Settings.from_env().thesis_vault_key


def seal_bytes(data: bytes, secret: str) -> bytes:
    return fernet(secret).encrypt(data)


def open_bytes(token: bytes, secret: str) -> bytes:
    try:
        return fernet(secret).decrypt(token.strip())
    except InvalidToken:
        raise VaultError("it doesn't open with THESIS_VAULT_KEY: another key sealed it, or it was changed") from None


def _week(week: str) -> str:
    if not WEEK.match(week):
        raise VaultError(f"not an ISO week: {week!r} (e.g. 2026-W44)")
    return week


def sealed_queue(week: str, root: Path = REPO_ROOT) -> Path:
    return root / "data" / "thesis_queue" / f"{_week(week)}.sealed"


def sealed_cards(week: str, root: Path = REPO_ROOT) -> Path:
    return root / "data" / "thesis_cards" / f"{_week(week)}.sealed"


def _write_sealed(path: Path, data: bytes, secret: str) -> bool:
    """Seal `data` to `path` unless the file there already opens to the same bytes; True when it was written."""
    if path.exists():
        try:
            if open_bytes(path.read_bytes(), secret) == data:
                return False
        except VaultError:
            pass  # sealed under another key: replaced
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(seal_bytes(data, secret) + b"\n")
    return True


def seal_queue(week: str, secret: str, root: Path = REPO_ROOT) -> bool:
    src = queue_path(_week(week), root)
    if not src.exists():
        raise VaultError(f"no queue file {src.name} to seal")
    return _write_sealed(sealed_queue(week, root), src.read_bytes(), secret)


def open_queue(week: str, secret: str, root: Path = REPO_ROOT) -> Path:
    src = sealed_queue(week, root)
    if not src.exists():
        raise VaultError(f"no sealed queue {src.name}")
    data = open_bytes(src.read_bytes(), secret)
    try:
        doc = json.loads(data)
    except ValueError as e:
        raise VaultError(f"{src.name} holds no queue document: {e}") from None
    if not isinstance(doc, dict) or doc.get("week") != week:
        raise VaultError(f"{src.name} holds another week's queue")
    out = queue_path(_week(week), root)
    out.write_bytes(data)
    return out


def card_files(week: str, root: Path = REPO_ROOT) -> dict[str, str]:
    """The week's card files in the working copy, by name (.json, .md and FAILED.md; anything else is left out)."""
    folder = cards_dir(_week(week), root)
    if not folder.is_dir():
        return {}
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.iterdir())
            if p.is_file() and CARD_FILE.match(p.name)}  # fmt: skip


def seal_cards(week: str, secret: str, root: Path = REPO_ROOT) -> tuple[bool, int]:
    """Seal the week's card files as one bundle; (written, number of files)."""
    files = card_files(week, root)
    if not files:
        raise VaultError(f"no card files in data/thesis_cards/{week}/ to seal")
    bundle = json.dumps({"week": week, "files": files}, ensure_ascii=False, sort_keys=True).encode()
    return _write_sealed(sealed_cards(week, root), bundle, secret), len(files)


def open_cards(week: str, secret: str, root: Path = REPO_ROOT) -> list[Path]:
    """Write the sealed bundle's files to data/thesis_cards/<week>/ (replacing what was there): the files must be the
    week's cards by name, or nothing is written."""
    src = sealed_cards(week, root)
    if not src.exists():
        raise VaultError(f"no sealed cards {src.name}")
    try:
        doc: Any = json.loads(open_bytes(src.read_bytes(), secret))
    except ValueError as e:
        raise VaultError(f"{src.name} holds no card bundle: {e}") from None
    files = doc.get("files") if isinstance(doc, dict) else None
    if not isinstance(doc, dict) or doc.get("week") != week or not isinstance(files, dict):
        raise VaultError(f"{src.name} holds no card bundle for {week}")
    bad = [n for n, t in files.items() if not (isinstance(n, str) and CARD_FILE.match(n) and isinstance(t, str))]
    if bad:
        raise VaultError(f"{src.name} holds {len(bad)} file(s) that aren't card files")
    folder = cards_dir(_week(week), root)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        if old.is_file() and CARD_FILE.match(old.name):
            old.unlink()
    out = []
    for name, text in sorted(files.items()):
        path = folder / name
        path.write_text(text, encoding="utf-8")
        out.append(path)
    return out


def sealed_weeks(root: Path = REPO_ROOT) -> list[str]:
    return sorted(p.stem for p in (root / "data" / "thesis_queue").glob("*-W*.sealed") if WEEK.match(p.stem))


def main(argv: list[str] | None = None, root: Path = REPO_ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    op = sub.add_parser("open", help="write the week's queue and cards (if sealed) as working copies")
    op.add_argument("--week", default=None, help="ISO week (default: the newest sealed queue)")
    se = sub.add_parser("seal", help="seal the week's cards (or, with --queue, its queue)")
    se.add_argument("--week", required=True, help="ISO week, e.g. 2026-W44")
    se.add_argument("--queue", action="store_true", help="seal data/thesis_queue/<week>.json instead")
    a = ap.parse_args(argv)
    secret = secret_from_env()
    if not secret:
        print("thesis vault: THESIS_VAULT_KEY is not set (BRIEF §2.4, Appendix G)", file=sys.stderr)
        return 1
    try:
        if a.cmd == "open":
            weeks = sealed_weeks(root)
            week = a.week or (weeks[-1] if weeks else None)
            if week is None:
                print("thesis vault: no sealed queue in data/thesis_queue/", file=sys.stderr)
                return 1
            q = open_queue(week, secret, root)
            cards = open_cards(week, secret, root) if sealed_cards(week, root).exists() else []
            print(f"thesis vault {week}: {q.relative_to(root)}"
                  + (f" and {len(cards)} card files in data/thesis_cards/{week}/" if cards else ""))  # fmt: skip
        elif a.queue:
            written = seal_queue(a.week, secret, root)
            print(f"thesis vault {a.week}: the queue {'sealed' if written else 'unchanged'}")
        else:
            written, n = seal_cards(a.week, secret, root)
            print(f"thesis vault {a.week}: {n} card files {'sealed' if written else 'unchanged'} -> "
                  f"{sealed_cards(a.week, root).relative_to(root)}")  # fmt: skip
    except VaultError as e:
        print(f"thesis vault: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

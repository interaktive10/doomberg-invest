"""The thesis vault (pipeline/thesis/vault.py; docs/SPEC_ISSUES.md 60): the repository is public, so git holds the
thesis queue and the cards only sealed. tests/db/test_thesis.py runs ingest and the fallback on sealed files."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline.thesis import queue, vault

KEY = "test-vault-key-0123456789abcdef"  # tests only; the live key is a GitHub secret (BRIEF §2.4)
OTHER = "another-vault-key-0123456789abcd"
ROOT = Path(__file__).resolve().parents[2]
W = "2026-W44"


def tree(tmp_path: Path) -> Path:
    """A week's working copies: the queue and two cards with their renderings, FAILED.md and a stray file."""
    (tmp_path / "data" / "thesis_queue").mkdir(parents=True)
    (tmp_path / "data" / "thesis_queue" / f"{W}.json").write_text(json.dumps({"week": W, "packs": [{"a": 1}]}))
    cards = tmp_path / "data" / "thesis_cards" / W
    cards.mkdir(parents=True)
    files = {"us-nmbs.json": '{"summary": "x"}', "us-nmbs.md": "# NMBS\n", "in-m-m.json": "{}", "in-m-m.md": "# M&M\n",
             "FAILED.md": "in-abc: no pack\n", "notes.txt": "scratch"}  # fmt: skip
    for name, text in files.items():
        (cards / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_a_sealed_file_opens_only_with_its_key_and_unchanged() -> None:
    token = vault.seal_bytes(b"Manzoor's research entry", KEY)
    assert b"research" not in token and vault.open_bytes(token, KEY) == b"Manzoor's research entry"
    assert vault.open_bytes(token + b"\n", KEY) == b"Manzoor's research entry"  # the file's trailing newline
    with pytest.raises(vault.VaultError, match="another key sealed it"):
        vault.open_bytes(token, OTHER)
    changed = token[:40] + (b"A" if token[40:41] != b"A" else b"B") + token[41:]
    with pytest.raises(vault.VaultError):
        vault.open_bytes(changed, KEY)


def test_a_short_key_is_refused() -> None:
    with pytest.raises(vault.VaultError, match="at least 24 characters"):
        vault.seal_bytes(b"x", "password123")


def test_the_queue_seals_and_opens_and_an_unchanged_queue_keeps_its_file(tmp_path: Path) -> None:
    root = tree(tmp_path)
    plain = root / "data" / "thesis_queue" / f"{W}.json"
    assert vault.seal_queue(W, KEY, root) is True
    sealed = vault.sealed_queue(W, root)
    first = sealed.read_bytes()
    assert b'"packs"' not in first and vault.seal_queue(W, KEY, root) is False and sealed.read_bytes() == first
    original = plain.read_bytes()
    plain.unlink()
    assert vault.open_queue(W, KEY, root) == plain and plain.read_bytes() == original
    plain.write_text(json.dumps({"week": W, "packs": []}))
    assert vault.seal_queue(W, KEY, root) is True and sealed.read_bytes() != first  # a changed queue is sealed again


def test_a_sealed_queue_of_another_week_is_refused(tmp_path: Path) -> None:
    root = tree(tmp_path)
    vault.seal_queue(W, KEY, root)
    shutil.copy(vault.sealed_queue(W, root), vault.sealed_queue("2026-W45", root))
    with pytest.raises(vault.VaultError, match="another week's queue"):
        vault.open_queue("2026-W45", KEY, root)
    with pytest.raises(vault.VaultError, match="not an ISO week"):
        vault.sealed_queue("../2026-W44", root)


def test_the_cards_are_one_bundle_that_names_no_card(tmp_path: Path) -> None:
    root = tree(tmp_path)
    written, n = vault.seal_cards(W, KEY, root)
    assert written and n == 5  # the stray notes.txt is left out
    bundle = vault.sealed_cards(W, root)
    assert bundle == root / "data" / "thesis_cards" / f"{W}.sealed"
    assert b"us-nmbs.json" not in bundle.read_bytes() and vault.seal_cards(W, KEY, root) == (False, 5)
    folder = root / "data" / "thesis_cards" / W
    shutil.rmtree(folder)
    opened = vault.open_cards(W, KEY, root)
    assert sorted(p.name for p in opened) == ["FAILED.md", "in-m-m.json", "in-m-m.md", "us-nmbs.json", "us-nmbs.md"]
    assert (folder / "in-m-m.md").read_text(encoding="utf-8") == "# M&M\n"


def test_opening_the_cards_replaces_the_working_copies(tmp_path: Path) -> None:
    root = tree(tmp_path)
    vault.seal_cards(W, KEY, root)
    folder = root / "data" / "thesis_cards" / W
    (folder / "us-zzz.json").write_text("{}")  # a card the bundle doesn't have
    (folder / "us-nmbs.json").write_text('{"summary": "edited"}')
    vault.open_cards(W, KEY, root)
    assert not (folder / "us-zzz.json").exists() and (folder / "us-nmbs.json").read_text() == '{"summary": "x"}'


@pytest.mark.parametrize("name", ["../../pipeline/thesis/validate.json", "sub/us-nmbs.json", ".hidden.json",
                                  "us-nmbs.py", "US-NMBS.json"])  # fmt: skip
def test_a_bundle_with_a_file_that_is_not_a_card_writes_nothing(tmp_path: Path, name: str) -> None:
    root = tree(tmp_path)
    doc = {"week": W, "files": {"us-nmbs.json": "{}", name: "x"}}
    vault.sealed_cards(W, root).write_bytes(vault.seal_bytes(json.dumps(doc).encode(), KEY))
    before = sorted(p.name for p in (root / "data" / "thesis_cards" / W).iterdir())
    with pytest.raises(vault.VaultError, match="aren't card files"):
        vault.open_cards(W, KEY, root)
    assert sorted(p.name for p in (root / "data" / "thesis_cards" / W).iterdir()) == before


def test_the_weekly_job_seals_the_queue_only_with_the_key(tmp_path: Path) -> None:
    doc = {"week": W, "week_end": "2026-10-30", "packs": [{"company": {"key": "us-nmbs"}}]}
    lines = queue.publish(doc, None, tmp_path)
    assert lines[-1] == queue.NO_KEY and lines[-1].startswith("::notice::")
    assert not vault.sealed_queue(W, tmp_path).exists()
    assert queue.publish(doc, KEY, tmp_path)[-1] == f"thesis queue {W}: sealed -> data/thesis_queue/{W}.sealed"
    assert queue.publish(doc, KEY, tmp_path)[-1].endswith("unchanged -> data/thesis_queue/2026-W44.sealed")
    assert json.loads(vault.open_bytes(vault.sealed_queue(W, tmp_path).read_bytes(), KEY)) == doc


def test_the_cli_opens_and_seals_with_the_key_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path)
    monkeypatch.delenv("THESIS_VAULT_KEY", raising=False)
    assert vault.main(["seal", "--week", W], root) == 1 and "THESIS_VAULT_KEY is not set" in capsys.readouterr().err
    monkeypatch.setenv("THESIS_VAULT_KEY", KEY)
    assert vault.main(["seal", "--week", W, "--queue"], root) == 0 and "the queue sealed" in capsys.readouterr().out
    assert vault.main(["seal", "--week", W], root) == 0
    assert f"5 card files sealed -> data/thesis_cards/{W}.sealed" in capsys.readouterr().out
    shutil.rmtree(root / "data" / "thesis_cards" / W)
    (root / "data" / "thesis_queue" / f"{W}.json").unlink()
    assert vault.main(["open"], root) == 0  # the newest sealed queue, and its cards
    assert "and 5 card files" in capsys.readouterr().out and (root / "data" / "thesis_cards" / W / "FAILED.md").exists()
    monkeypatch.setenv("THESIS_VAULT_KEY", OTHER)
    assert vault.main(["open", "--week", W], root) == 1 and "another key sealed it" in capsys.readouterr().err


def git(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    except OSError as e:
        pytest.skip(f"no git: {e}")
    if r.returncode > 1:
        pytest.skip(f"not a git checkout: {r.stderr.strip()}")
    return r


def test_git_tracks_no_plaintext_queue_or_card() -> None:
    """The working copies are gitignored, and none is tracked (W39-W43's plaintext queues were removed)."""
    tracked = git("ls-files", "data/thesis_queue", "data/thesis_cards").stdout.split()
    assert tracked and all(p.endswith((".sealed", ".gitkeep")) for p in tracked), tracked
    plain = [f"data/thesis_queue/{W}.json", f"data/thesis_cards/{W}/us-nmbs.json", f"data/thesis_cards/{W}/FAILED.md"]
    assert git("check-ignore", *plain).stdout.split() == plain
    assert git("check-ignore", f"data/thesis_queue/{W}.sealed", f"data/thesis_cards/{W}.sealed").stdout == ""

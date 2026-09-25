"""M0-02: the guard passes on the repository and fails on every seeded case (BRIEF Appendix E). PROTECTED."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "tests" / "guard" / "cases"
sys.path.insert(0, str(ROOT / "scripts"))

import guard  # noqa: E402

# case file -> (where it is planted in a scratch repo, rule that must fire)
SEEDED: dict[str, tuple[str, str]] = {
    "broker_import.py": ("pipeline/us/scratch_broker.py", "BANNED_PY_PACKAGE"),
    "anthropic_import.py": ("pipeline/scratch_anthropic.py", "BANNED_PY_PACKAGE"),
    "paid_domain.py": ("pipeline/net/scratch_domain.py", "BANNED_DOMAIN"),
    "order_identifier.py": ("pipeline/scratch_orders.py", "ORDER_IDENTIFIER"),
    "journal_to_llm.py": ("pipeline/llm/scratch_prompt.py", "PRIVACY"),
    "pit_bypass.py": ("pipeline/signals/scratch_pit.py", "PIT_READ"),
    "pit_multiline.py": ("pipeline/signals/scratch_pit2.py", "PIT_READ"),  # review F7 (M2): the reads the guard missed
    "pit_from_underscore.py": ("web/lib/scratch_pit.py", "PIT_READ"),
    "pit_table_copy.py": ("scripts/scratch_pit.py", "PIT_READ"),
    "pit_fstring.py": ("pipeline/lab/scratch_pit.py", "PIT_READ"),
    "openai_default_base.py": ("pipeline/llm/providers/scratch_openai.py", "OPENAI_CLIENT"),
    "npm_anthropic.ts": ("web/lib/scratch.ts", "BANNED_NPM_PACKAGE"),
}


@pytest.fixture()
def scratch_repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for f in ("guards.yaml", "quotas.yaml"):
        shutil.copy(ROOT / "config" / f, tmp_path / "config" / f)
    (tmp_path / "pipeline").mkdir()
    return tmp_path


def test_repository_is_clean() -> None:
    violations = guard.run(ROOT)
    assert violations == [], "\n".join(map(str, violations))


def test_every_case_file_is_seeded() -> None:
    assert sorted(p.name for p in CASES.iterdir() if p.is_file()) == sorted(SEEDED)


@pytest.mark.parametrize("case", sorted(SEEDED))
def test_seeded_case_fails(scratch_repo: Path, case: str) -> None:
    target, rule = SEEDED[case]
    dest = scratch_repo / target
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(CASES / case, dest)
    violations = guard.run(scratch_repo)
    assert any(v.rule == rule for v in violations), f"{case}: expected {rule}, got {violations}"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/guard.py"), "--root", str(scratch_repo)], capture_output=True, text=True
    )
    assert proc.returncode == 1


def test_clean_scratch_repo_passes(scratch_repo: Path) -> None:
    (scratch_repo / "pipeline" / "ok.py").write_text("import httpx\n", encoding="utf-8")
    assert guard.run(scratch_repo) == []


def test_banned_dependency_in_pyproject(scratch_repo: Path) -> None:
    (scratch_repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["polars", "Kite_Connect>=1"]\n'
        '[dependency-groups]\ndev = ["anthropic"]\n',
        encoding="utf-8",
    )
    # "Kite_Connect" normalizes to kite-connect (not banned); "anthropic" is banned.
    rules = [v.message for v in guard.run(scratch_repo)]
    assert rules == ["dependency anthropic"]


def test_banned_package_in_uv_lock(scratch_repo: Path) -> None:
    (scratch_repo / "uv.lock").write_text('[[package]]\nname = "ccxt"\nversion = "4.0"\n', encoding="utf-8")
    assert [v.rule for v in guard.run(scratch_repo)] == ["BANNED_PY_PACKAGE"]


def test_banned_npm_dependency(scratch_repo: Path) -> None:
    (scratch_repo / "web").mkdir()
    (scratch_repo / "web" / "package.json").write_text('{"dependencies": {"openai": "^4"}}', encoding="utf-8")
    assert [v.rule for v in guard.run(scratch_repo)] == ["BANNED_NPM_PACKAGE"]


def test_dynamic_import_is_caught(scratch_repo: Path) -> None:
    (scratch_repo / "pipeline" / "dyn.py").write_text(
        'import importlib\nm = importlib.import_module("ib_insync")\n', encoding="utf-8"
    )
    assert [v.rule for v in guard.run(scratch_repo)] == ["BANNED_PY_PACKAGE"]


def test_openai_client_with_openrouter_url_is_allowed(scratch_repo: Path) -> None:
    (scratch_repo / "pipeline" / "or.py").write_text(
        'from openai import OpenAI\nc = OpenAI(base_url="https://openrouter.ai/api/v1", api_key="k")\n'
        "d = OpenAI(base_url=cfg.openrouter_base_url, api_key='k')\n",
        encoding="utf-8",
    )
    assert guard.run(scratch_repo) == []


def test_openai_client_with_other_url_fails(scratch_repo: Path) -> None:
    (scratch_repo / "pipeline" / "bad.py").write_text(
        'from openai import OpenAI\nc = OpenAI(base_url="https://example.com/v1")\n', encoding="utf-8"
    )
    assert [v.rule for v in guard.run(scratch_repo)] == ["OPENAI_CLIENT"]


def test_excluded_paths_are_skipped(scratch_repo: Path) -> None:
    dest = scratch_repo / "fixtures" / "x.py"
    dest.parent.mkdir()
    dest.write_text("import kiteconnect\n", encoding="utf-8")
    assert guard.run(scratch_repo) == []


def test_pit_owner_may_read(scratch_repo: Path) -> None:
    dest = scratch_repo / "pipeline" / "db" / "pit.py"
    dest.parent.mkdir()
    dest.write_text('SQL = "select * from fundamentals_q where filed_at <= %s"\n', encoding="utf-8")
    assert guard.run(scratch_repo) == []


def test_syntax_error_does_not_hide_import(scratch_repo: Path) -> None:
    (scratch_repo / "pipeline" / "broken.py").write_text("import kiteconnect\ndef (:\n", encoding="utf-8")
    assert [v.rule for v in guard.run(scratch_repo)] == ["BANNED_PY_PACKAGE"]


def test_paths_mode_outside_repo_is_ignored(scratch_repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside") / "x.py"
    outside.write_text("import kiteconnect\n", encoding="utf-8")
    assert guard.run(scratch_repo, [outside]) == []


def test_pit_rule_reports_each_bypass_on_its_line(scratch_repo: Path) -> None:
    """Review F7 (M2): multi-line SQL, .from_(), COPY/TABLE and a table name held in a variable are all reads."""
    dest = scratch_repo / "pipeline" / "x.py"
    dest.write_text((CASES / "pit_table_copy.py").read_text(encoding="utf-8") + (CASES / "pit_multiline.py").read_text(
        encoding="utf-8"), encoding="utf-8")  # fmt: skip
    got = sorted((v.line, v.rule) for v in guard.run(scratch_repo))
    assert got == [(1, "PIT_READ"), (2, "PIT_READ"), (5, "PIT_READ")]
    writer = scratch_repo / "pipeline" / "db" / "repo.py"  # the repository may name tables to write them
    writer.parent.mkdir(parents=True)
    writer.write_text('INSERT = "insert into fundamentals_q"\nTABLE = "fundamentals_q"\n', encoding="utf-8")
    dest.unlink()
    assert guard.run(scratch_repo) == []

"""Regression: `uv run` exits 1 when it can't sync (package index unreachable). The hook used to read that as a
guard violation and block every edit. Now it falls back to the system interpreter and still blocks real violations.
Kept outside tests/guard/ (protected) because it covers scripts/guard_hook.py, which is not a protected path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "scripts" / "guard_hook.py"


def _project_with_broken_uv(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    (tmp_path / "config").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "pipeline").mkdir()
    for f in ("guards.yaml", "quotas.yaml"):
        shutil.copy(ROOT / "config" / f, tmp_path / "config" / f)
    shutil.copy(ROOT / "scripts" / "guard.py", tmp_path / "scripts" / "guard.py")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\nversion = '0'\n", encoding="utf-8")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_uv = bindir / "uv"
    fake_uv.write_text("#!/bin/sh\necho '  x Failed to download `lxml==6.1.3`' >&2\nexit 1\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    return tmp_path, env


def _run(env: dict[str, str], file_path: Path) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(file_path)}})
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env)


def test_uv_sync_failure_is_not_a_violation(tmp_path: Path) -> None:
    project, env = _project_with_broken_uv(tmp_path)
    f = project / "pipeline" / "clean.py"
    f.write_text("import httpx\n", encoding="utf-8")
    p = _run(env, f)
    assert p.returncode == 0, p.stderr


def test_real_violation_still_blocks_when_uv_fails(tmp_path: Path) -> None:
    project, env = _project_with_broken_uv(tmp_path)
    f = project / "pipeline" / "bad.py"
    f.write_text("import kiteconnect\n", encoding="utf-8")
    p = _run(env, f)
    assert p.returncode == 2, p.stderr
    assert "kiteconnect" in p.stderr

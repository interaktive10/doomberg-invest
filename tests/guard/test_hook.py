"""M0-03: the PostToolUse hook exits 2 on an edit adding `import kiteconnect` (BRIEF Appendix C). PROTECTED."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "guard_hook.py"


def _scratch(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "scripts").mkdir()
    for f in ("guards.yaml", "quotas.yaml"):
        shutil.copy(ROOT / "config" / f, tmp_path / "config" / f)
    shutil.copy(ROOT / "scripts" / "guard.py", tmp_path / "scripts" / "guard.py")
    (tmp_path / "pipeline").mkdir()
    return tmp_path


def _run_hook(project: Path, payload: object) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    # The scratch tree has no pyproject.toml, so the hook falls back to sys.executable (which has pyyaml).
    return subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=120
    )


def test_hook_blocks_kiteconnect(tmp_path: Path) -> None:
    project = _scratch(tmp_path)
    f = project / "pipeline" / "edited.py"
    f.write_text("import kiteconnect\n", encoding="utf-8")
    p = _run_hook(project, {"tool_name": "Write", "tool_input": {"file_path": str(f)}})
    assert p.returncode == 2, p.stderr
    assert "kiteconnect" in p.stderr


def test_hook_allows_clean_edit(tmp_path: Path) -> None:
    project = _scratch(tmp_path)
    f = project / "pipeline" / "edited.py"
    f.write_text("import httpx\n", encoding="utf-8")
    p = _run_hook(project, {"tool_name": "Edit", "tool_input": {"file_path": str(f)}})
    assert p.returncode == 0, p.stderr


def test_hook_never_breaks_session_on_bad_input(tmp_path: Path) -> None:
    project = _scratch(tmp_path)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    p = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, env=env)
    assert p.returncode == 0
    assert "warning" in p.stderr


def test_hook_ignores_payload_without_file(tmp_path: Path) -> None:
    project = _scratch(tmp_path)
    assert _run_hook(project, {"tool_name": "Bash", "tool_input": {"command": "ls"}}).returncode == 0

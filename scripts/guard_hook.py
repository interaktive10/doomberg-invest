#!/usr/bin/env python3
"""Claude Code PostToolUse hook (BRIEF Appendix C): run the guard on the file just edited.

Exit 2 with violations on stderr (Claude sees them and must fix); exit 0 otherwise.
Any internal error -> exit 0 with a warning: the hook must never break the session.
Runs with the system python3, so it shells out to guard.py through `uv run` when available.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def guard_command(root: Path, file_path: str) -> list[str]:
    """The guard invocation. `--frozen` matters: a plain `uv run` right after an edit to pyproject.toml would
    re-lock uv.lock and install the new dependency (even a banned one) before the guard gets to flag it."""
    py = (
        ["uv", "run", "--frozen", "--quiet", "python"]
        if shutil.which("uv") and (root / "pyproject.toml").exists()
        else [sys.executable]
    )
    return [*py, str(root / "scripts" / "guard.py"), "--root", str(root), "--paths", file_path]


def _is_violation(proc: subprocess.CompletedProcess[str]) -> bool:
    """guard.py exits 1 on violations and always ends stderr with its summary line. `uv run` also exits 1 when it
    can't sync (e.g. the package index is unreachable), which must not read as a violation."""
    return proc.returncode == 1 and "guard: " in proc.stderr and "violation(s)" in proc.stderr


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        file_path = (payload.get("tool_input") or {}).get("file_path")
        if not file_path:
            return 0
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parent.parent)
        cmd = guard_command(root, str(file_path))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=root)
        if proc.returncode != 0 and not _is_violation(proc) and cmd[0] == "uv":
            # uv itself failed (not the guard): the guard needs only pyyaml, so retry with this interpreter.
            cmd = [sys.executable, *cmd[cmd.index("python") + 1 :]]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=root)
        if _is_violation(proc):
            sys.stderr.write(proc.stderr)
            return 2
        if proc.returncode != 0:
            sys.stderr.write(f"guard_hook warning: guard exited {proc.returncode}: {proc.stderr[-500:]}\n")
        return 0
    except Exception as e:  # noqa: BLE001 — never break the session
        sys.stderr.write(f"guard_hook warning: {type(e).__name__}: {e}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())

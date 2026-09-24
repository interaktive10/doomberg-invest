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


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        file_path = (payload.get("tool_input") or {}).get("file_path")
        if not file_path:
            return 0
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parent.parent)
        guard = root / "scripts" / "guard.py"
        py = (
            ["uv", "run", "--quiet", "python"]
            if shutil.which("uv") and (root / "pyproject.toml").exists()
            else [sys.executable]
        )
        proc = subprocess.run(
            [*py, str(guard), "--root", str(root), "--paths", str(file_path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=root,
        )
        if proc.returncode == 1:
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

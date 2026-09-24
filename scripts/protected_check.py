#!/usr/bin/env python3
"""Protected-path check (BRIEF Appendix D).

Fails (exit 1) when a changed file matches a protected path and the PR lacks the `human-approved` label.

  protected_check.py --base origin/main --labels "a,b"      # uses git diff --name-only BASE...HEAD
  protected_check.py --files f1 f2 --labels ""              # synthetic diffs (tests)
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys

PROTECTED: tuple[str, ...] = (
    "config/guards.yaml",
    "config/signals.yaml",
    "config/weights.yaml",
    "config/context.yaml",
    "config/redflags.yaml",
    "scripts/guard.py",
    "tests/guard/**",
    "pipeline/llm/privacy.py",
    "pipeline/db/pit.py",
    ".claude/agents/reviewer.md",
    "docs/BRIEF.md",
)
LABEL = "human-approved"


def is_protected(path: str) -> bool:
    for pat in PROTECTED:
        if pat.endswith("/**"):
            if path.startswith(pat[:-2]):
                return True
        elif fnmatch.fnmatchcase(path, pat):
            return True
    return False


def evaluate(files: list[str], labels: list[str]) -> tuple[bool, list[str]]:
    hits = sorted({f for f in files if is_protected(f)})
    ok = not hits or LABEL in labels
    return ok, hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--base")
    g.add_argument("--files", nargs="*")
    ap.add_argument("--labels", default="", help="comma-separated PR labels")
    a = ap.parse_args(argv)
    if a.base:
        # --no-renames: a rename must show as delete + add, or moving a protected file away would list only its
        # new, unprotected path and slip past the check.
        diff = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", f"{a.base}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [ln for ln in diff.stdout.splitlines() if ln.strip()]
    else:
        files = list(a.files or [])
    labels = [x.strip() for x in a.labels.split(",") if x.strip()]
    ok, hits = evaluate(files, labels)
    if hits and ok:
        print(f"protected: {len(hits)} protected file(s) changed; `{LABEL}` label present")
    if not ok:
        print(f"protected: these files need the `{LABEL}` label:", file=sys.stderr)
        for h in hits:
            print(f"  {h}", file=sys.stderr)
        return 1
    if not hits:
        print("protected: no protected paths changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

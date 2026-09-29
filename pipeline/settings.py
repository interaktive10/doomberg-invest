"""Runtime settings from the environment (BRIEF §2.4). No secrets have defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = "postgresql://doom:doom@localhost:5432/doom"  # local dev DB from scripts/session_start.sh


def _flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    mock_externals: bool
    sec_user_agent: str | None
    cache_dir: Path
    # free-tier keys (BRIEF §0.5, §2.6); a provider without its key is skipped by the router
    gemini_api_key: str | None = field(default=None, repr=False)
    groq_api_key: str | None = field(default=None, repr=False)
    openrouter_api_key: str | None = field(default=None, repr=False)
    eia_api_key: str | None = field(default=None, repr=False)
    stooq_api_key: str | None = field(default=None, repr=False)  # Stooq's CSV needs one since 2026 (net/stooq.py)

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            mock_externals=_flag("MOCK_EXTERNALS"),
            sec_user_agent=os.environ.get("SEC_USER_AGENT") or None,
            cache_dir=Path(os.environ.get("DOOM_CACHE_DIR", REPO_ROOT / ".cache")),
            gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
            groq_api_key=os.environ.get("GROQ_API_KEY") or None,
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
            eia_api_key=os.environ.get("EIA_API_KEY") or None,
            stooq_api_key=os.environ.get("STOOQ_API_KEY") or None,
        )

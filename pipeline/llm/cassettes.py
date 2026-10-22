"""Cassettes (BRIEF §9): recorded provider responses that make LLM tests offline and repeatable.

`record-cassettes.yml` runs the F-SYN corpus (P-01) and the P-02, P-06 and P-07 samples
(pipeline.facts.samples) through the real free-tier providers
with a `Recorder` around each client; every request/response pair is written to
pipeline/llm/cassettes/<prompt>/<key>.json, where the key is a hash of the whole request (provider, model, prompt,
system and user text, schema, mode, temperature). `Player` serves them back: a request that wasn't recorded is a
ProviderError ("cassette miss"), so a changed prompt or document can never replay a stale answer.

MANIFEST.sha256 lists each cassette's sha256; tests check every file against it, so a hand-edited cassette fails
(CLAUDE.md: never hand-edit cassettes). The request body is stored without any key (keys travel in headers).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.llm.providers.base import Completion, Provider, ProviderError, Request

CASSETTE_DIR = Path(__file__).resolve().parent / "cassettes"
MANIFEST = "MANIFEST.sha256"


def request_key(provider: str, req: Request) -> str:
    doc = {"provider": provider, "model": req.model, "prompt_id": req.prompt_id, "system": req.system,
           "user": req.user, "schema": req.schema, "mode": req.mode, "tool_name": req.tool_name,
           "temperature": req.temperature}  # fmt: skip
    return hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def path_for(root: Path, provider: str, req: Request) -> Path:
    return root / req.prompt_id / f"{provider}-{request_key(provider, req)[:24]}.json"


@dataclass
class Recorder:
    """Wraps a real provider and writes every successful exchange."""

    inner: Provider
    root: Path = CASSETTE_DIR

    @property
    def name(self) -> str:
        return self.inner.name

    def available(self) -> bool:
        return self.inner.available()

    def complete(self, req: Request) -> Completion:
        c = self.inner.complete(req)
        p = path_for(self.root, self.name, req)
        p.parent.mkdir(parents=True, exist_ok=True)
        doc = {"key": request_key(self.name, req), "provider": self.name, "prompt_id": req.prompt_id,
               "model": req.model, "request": {"system": req.system, "user": req.user},
               "response": {"content": c.content, "tokens_in": c.tokens_in, "tokens_out": c.tokens_out}}  # fmt: skip
        p.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        return c


@dataclass
class Player:
    """Serves recorded responses for one provider name."""

    name: str
    root: Path = CASSETTE_DIR

    def available(self) -> bool:
        return True

    def complete(self, req: Request) -> Completion:
        p = path_for(self.root, self.name, req)
        if not p.exists():
            raise ProviderError(f"{self.name}: cassette miss for {req.prompt_id}")
        doc: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
        if doc.get("key") != request_key(self.name, req):
            raise ProviderError(f"{self.name}: cassette key mismatch at {p.name}")
        r = doc["response"]
        return Completion(dict(r["content"]), r.get("tokens_in"), r.get("tokens_out"))


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.json") if p.is_file())


def write_manifest(root: Path = CASSETTE_DIR) -> Path:
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}" for p in _files(root)]
    out = root / MANIFEST
    out.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return out


def manifest_problems(root: Path = CASSETTE_DIR) -> list[str]:
    """Differences between the cassettes on disk and MANIFEST.sha256 (empty = consistent)."""
    m = root / MANIFEST
    listed: dict[str, str] = {}
    if m.exists():
        for line in m.read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, name = line.split(maxsplit=1)
                listed[name] = digest
    problems = []
    on_disk = {p.relative_to(root).as_posix(): p for p in _files(root)}
    for name, p in on_disk.items():
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if name not in listed:
            problems.append(f"{name}: not in {MANIFEST}")
        elif listed[name] != digest:
            problems.append(f"{name}: sha256 differs from {MANIFEST} (edited by hand?)")
    problems += [f"{name}: listed in {MANIFEST} but missing" for name in sorted(set(listed) - set(on_disk))]
    return problems


def recorded(root: Path = CASSETTE_DIR, prompt_id: str | None = None) -> int:
    base = root / prompt_id if prompt_id else root
    return len(_files(base)) if base.exists() else 0

#!/usr/bin/env python3
"""Repository guard (BRIEF Appendix E). PROTECTED path.

Enforces, from config/guards.yaml:
  - banned Python packages (imports in scanned code + the root manifests pyproject.toml / uv.lock)
  - banned npm packages (web/package.json + JS/TS imports in scanned code)
  - banned runtime domains (any scanned text file)
  - banned order-placement identifiers (any scanned code file)
  - openai_client_rule: OpenAI(...) / AsyncOpenAI(...) must pass base_url = the OpenRouter base URL
  - pit_rule: SQL/ORM reads of point-in-time tables only inside pipeline/db/pit.py
  - privacy_rule: pipeline/llm/** and pipeline/thesis/evidence_pack.py never reference journal data

Usage:
  guard.py                     scan the whole repository (scan_paths + root manifests)
  guard.py --paths a.py b.ts   check only these files (used by the PostToolUse hook)
  guard.py --root DIR          treat DIR as the repository root (tests use a temp tree)
Exit 0 = clean, 1 = violations (printed one per line as path:line: RULE message).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sql"}
TEXT_SUFFIXES = CODE_SUFFIXES | {".yaml", ".yml", ".json", ".toml", ".sh", ".md", ".txt", ".env", ".cfg", ".ini"}
ROOT_MANIFESTS = ("pyproject.toml", "uv.lock", "web/package.json")
PIT_OWNER = "pipeline/db/pit.py"
PIT_TABLES = ("fundamentals_q", "ownership_q", "insider_events", "corp_events")
PRIVACY_SCOPE_DIRS = ("pipeline/llm/",)
PRIVACY_SCOPE_FILES = ("pipeline/thesis/evidence_pack.py",)
PRIVACY_TERMS = re.compile(r"journal|postmortem|post_mortem|portfolio_pct", re.IGNORECASE)

# Distribution name -> top-level import name(s), for banned Python packages whose import differs.
IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "alpaca-py": ("alpaca",),
    "alpaca-trade-api": ("alpaca_trade_api",),
    "ib-async": ("ib_async",),
    "smartapi-python": ("SmartApi", "smartapi"),
    "upstox-python-sdk": ("upstox_client",),
    "fyers-apiv3": ("fyers_apiv3",),
    "breeze-connect": ("breeze_connect",),
    "schwab-py": ("schwab",),
    "tda-api": ("tda",),
}


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


@dataclass(frozen=True)
class GuardConfig:
    scan_paths: tuple[str, ...]
    exclude_paths: tuple[str, ...]
    py_packages: tuple[str, ...]
    npm_packages: tuple[str, ...]
    domains: tuple[str, ...]
    identifiers: tuple[str, ...]
    openrouter_base_url: str | None

    @classmethod
    def load(cls, root: Path) -> GuardConfig:
        g: dict[str, Any] = yaml.safe_load((root / "config/guards.yaml").read_text(encoding="utf-8"))
        base_url: str | None = None
        quotas = root / "config/quotas.yaml"
        if quotas.exists():
            q: dict[str, Any] = yaml.safe_load(quotas.read_text(encoding="utf-8")) or {}
            base_url = ((q.get("providers") or {}).get("openrouter") or {}).get("base_url")
        return cls(
            scan_paths=tuple(g["scan_paths"]),
            exclude_paths=tuple(g["exclude_paths"]),
            py_packages=tuple(g["banned_python_packages"]),
            npm_packages=tuple(g["banned_npm_packages"]),
            domains=tuple(g["banned_runtime_domains"]),
            identifiers=tuple(g["banned_code_identifiers"]),
            openrouter_base_url=base_url,
        )


def _norm_dist(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _banned_imports(cfg: GuardConfig) -> dict[str, str]:
    """import top-level name -> banned distribution."""
    out: dict[str, str] = {}
    for dist in cfg.py_packages:
        for imp in IMPORT_NAMES.get(dist, (dist.replace("-", "_"),)):
            out[imp] = dist
    return out


def _rel(root: Path, p: Path) -> str:
    return p.resolve().relative_to(root.resolve()).as_posix()


def _is_excluded(rel: str, cfg: GuardConfig) -> bool:
    return any(rel == e or rel.startswith(e.rstrip("/") + "/") for e in cfg.exclude_paths)


def _in_scan_paths(rel: str, cfg: GuardConfig) -> bool:
    return any(rel == s or rel.startswith(s.rstrip("/") + "/") for s in cfg.scan_paths)


def iter_repo_files(root: Path, cfg: GuardConfig) -> Iterator[Path]:
    for s in cfg.scan_paths:
        base = root / s
        if base.is_file():
            yield base
        elif base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file() and "node_modules" not in p.parts and "__pycache__" not in p.parts:
                    yield p
    for m in ROOT_MANIFESTS:
        if (root / m).is_file():
            yield root / m


# ---------------------------------------------------------------- individual checks


def check_python_imports(rel: str, text: str, cfg: GuardConfig) -> list[Violation]:
    banned = _banned_imports(cfg)
    out: list[Violation] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # Unparseable: fall back to a line regex so a syntax error can't hide an import.
        for i, line in enumerate(text.splitlines(), 1):
            m = re.match(r"\s*(?:from|import)\s+([A-Za-z_][\w]*)", line)
            if m and m.group(1) in banned:
                out.append(Violation(rel, i, "BANNED_PY_PACKAGE", f"import of {banned[m.group(1)]}"))
        return out
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module.split(".")[0]]
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name | ast.Attribute)
            and (getattr(node.func, "id", None) or getattr(node.func, "attr", None)) in {"import_module", "__import__"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names = [node.args[0].value.split(".")[0]]
        for n in names:
            if n in banned:
                out.append(Violation(rel, getattr(node, "lineno", 1), "BANNED_PY_PACKAGE", f"import of {banned[n]}"))
    return out


def check_openai_client(rel: str, text: str, cfg: GuardConfig) -> list[Violation]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
        if fname not in {"OpenAI", "AsyncOpenAI"}:
            continue
        kw = next((k for k in node.keywords if k.arg == "base_url"), None)
        if kw is None:
            out.append(Violation(rel, node.lineno, "OPENAI_CLIENT", "OpenAI(...) without base_url (OpenRouter only)"))
            continue
        v = kw.value
        if isinstance(v, ast.Constant):
            if v.value != cfg.openrouter_base_url:
                out.append(
                    Violation(rel, node.lineno, "OPENAI_CLIENT", f"base_url {v.value!r} is not the OpenRouter URL")
                )
        elif "openrouter" not in ast.unparse(v).lower():
            out.append(
                Violation(
                    rel, node.lineno, "OPENAI_CLIENT", "base_url must come from config/quotas.yaml openrouter.base_url"
                )
            )
    return out


_JS_IMPORT = re.compile(r"""(?:from\s+|require\(\s*|import\(\s*|import\s+)['"]([^'"]+)['"]""")


def check_js_imports(rel: str, text: str, cfg: GuardConfig) -> list[Violation]:
    out: list[Violation] = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in _JS_IMPORT.finditer(line):
            spec = m.group(1)
            pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
            if pkg in cfg.npm_packages:
                out.append(Violation(rel, i, "BANNED_NPM_PACKAGE", f"import of {pkg}"))
    return out


def check_domains(rel: str, text: str, cfg: GuardConfig) -> list[Violation]:
    out: list[Violation] = []
    for i, line in enumerate(text.splitlines(), 1):
        for d in cfg.domains:
            if re.search(r"(?<![\w.-])" + re.escape(d) + r"(?![\w-])", line):
                out.append(Violation(rel, i, "BANNED_DOMAIN", d))
    return out


def check_identifiers(rel: str, text: str, cfg: GuardConfig) -> list[Violation]:
    out: list[Violation] = []
    for i, line in enumerate(text.splitlines(), 1):
        for ident in cfg.identifiers:
            if re.search(r"\b" + re.escape(ident) + r"\b", line):
                out.append(Violation(rel, i, "ORDER_IDENTIFIER", ident))
    return out


_PIT_SQL = re.compile(r"\b(?:from|join)\s+(?:public\.)?\"?(" + "|".join(PIT_TABLES) + r")\b", re.IGNORECASE)
_PIT_ORM = re.compile(r"""\.(?:from|table)\(\s*['"](""" + "|".join(PIT_TABLES) + r""")['"]""")


def check_pit(rel: str, text: str) -> list[Violation]:
    if rel == PIT_OWNER or rel.startswith("db/migrations/"):
        return []
    out: list[Violation] = []
    for i, line in enumerate(text.splitlines(), 1):
        m = _PIT_SQL.search(line) or _PIT_ORM.search(line)
        if m:
            out.append(Violation(rel, i, "PIT_READ", f"direct read of {m.group(1)} outside {PIT_OWNER} (use as_of())"))
    return out


def check_privacy(rel: str, text: str) -> list[Violation]:
    if not (rel.startswith(PRIVACY_SCOPE_DIRS) or rel in PRIVACY_SCOPE_FILES):
        return []
    out: list[Violation] = []
    for i, line in enumerate(text.splitlines(), 1):
        m = PRIVACY_TERMS.search(line)
        if m:
            out.append(Violation(rel, i, "PRIVACY", f"reference to private data ({m.group(0)}) in LLM-facing module"))
    return out


def check_pyproject(rel: str, text: str, cfg: GuardConfig) -> list[Violation]:
    banned = {_norm_dist(p) for p in cfg.py_packages}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return [Violation(rel, 1, "MANIFEST", f"unparseable: {e}")]
    deps: list[str] = list((data.get("project") or {}).get("dependencies") or [])
    for group in (data.get("dependency-groups") or {}).values():
        deps.extend(d for d in group if isinstance(d, str))
    for extra in ((data.get("project") or {}).get("optional-dependencies") or {}).values():
        deps.extend(extra)
    out: list[Violation] = []
    for d in deps:
        name = _norm_dist(re.split(r"[\s\[<>=!~;]", d, maxsplit=1)[0])
        if name in banned:
            line = next((i for i, ln in enumerate(text.splitlines(), 1) if d in ln), 1)
            out.append(Violation(rel, line, "BANNED_PY_PACKAGE", f"dependency {name}"))
    return out


def check_uv_lock(rel: str, text: str, cfg: GuardConfig) -> list[Violation]:
    banned = {_norm_dist(p) for p in cfg.py_packages}
    out: list[Violation] = []
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r'name = "([^"]+)"', line)
        if m and _norm_dist(m.group(1)) in banned:
            out.append(Violation(rel, i, "BANNED_PY_PACKAGE", f"locked package {m.group(1)}"))
    return out


def check_package_json(rel: str, text: str, cfg: GuardConfig) -> list[Violation]:
    try:
        data: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as e:
        return [Violation(rel, 1, "MANIFEST", f"unparseable: {e}")]
    out: list[Violation] = []
    for sec in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        for name in data.get(sec) or {}:
            if name in cfg.npm_packages:
                out.append(Violation(rel, 1, "BANNED_NPM_PACKAGE", f"{sec}: {name}"))
    return out


# ---------------------------------------------------------------- driver


def check_file(root: Path, path: Path, cfg: GuardConfig) -> list[Violation]:
    try:
        rel = _rel(root, path)
    except ValueError:  # outside the repository: not ours to judge
        return []
    if _is_excluded(rel, cfg):
        return []
    is_manifest = rel in ROOT_MANIFESTS
    if not is_manifest and not _in_scan_paths(rel, cfg):
        return []
    if path.suffix not in TEXT_SUFFIXES and path.name not in {"Makefile", "Dockerfile"} and not is_manifest:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    if rel == "pyproject.toml":
        return check_pyproject(rel, text, cfg)
    if rel == "uv.lock":
        return check_uv_lock(rel, text, cfg)
    out: list[Violation] = []
    if rel == "web/package.json":
        out += check_package_json(rel, text, cfg)
    out += check_domains(rel, text, cfg)
    if path.suffix in CODE_SUFFIXES:
        out += check_identifiers(rel, text, cfg)
        out += check_pit(rel, text)
        out += check_privacy(rel, text)
    if path.suffix == ".py":
        out += check_python_imports(rel, text, cfg)
        out += check_openai_client(rel, text, cfg)
    if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
        out += check_js_imports(rel, text, cfg)
    return out


def run(root: Path, paths: Iterable[Path] | None = None) -> list[Violation]:
    cfg = GuardConfig.load(root)
    files = (
        [p if p.is_absolute() else root / p for p in paths] if paths is not None else list(iter_repo_files(root, cfg))
    )
    out: list[Violation] = []
    for f in files:
        if f.is_file():
            out.extend(check_file(root, f, cfg))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--paths", nargs="*", type=Path, default=None)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    violations = run(root, args.paths)
    for v in violations:
        print(v, file=sys.stderr)
    if violations:
        print(f"guard: {len(violations)} violation(s)", file=sys.stderr)
        return 1
    print("guard: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())

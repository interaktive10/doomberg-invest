"""F-LAB: the synthetic panel generator (fixtures/lab/make_lab.py), loaded once per session."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

GENERATOR = Path(__file__).resolve().parents[2] / "fixtures" / "lab" / "make_lab.py"


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_lab", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_lab"] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def f_lab() -> ModuleType:
    return load_generator()

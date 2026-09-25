"""Scheduled workflows (BRIEF §2.5): step order that the pipeline depends on."""

from __future__ import annotations

from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def steps(name: str, job: str) -> list[str]:
    doc = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
    return [str(s.get("run", "")) for s in doc["jobs"][job]["steps"]]


def test_13f_runs_before_the_universe_re_seed() -> None:
    """Review F9 (M2): the re-seed puts every listed filer back in the universe until the next weekly run, so 13F
    must map CUSIPs before it."""
    runs = steps("quarterly.yml", "us")
    thirteen_f = next(i for i, r in enumerate(runs) if "pipeline.us.quarterly" in r)
    seed = next(i for i, r in enumerate(runs) if "pipeline.db.seed" in r)
    assert thirteen_f < seed


def test_every_pipeline_job_migrates_first() -> None:
    for name, jobs in (("daily.yml", ("us",)), ("weekly.yml", ("us",)), ("quarterly.yml", ("us",))):
        for job in jobs:
            runs = [r for r in steps(name, job) if "python -m pipeline" in r]
            assert runs and "pipeline.db.migrate" in runs[0], (name, job)


def test_size_guard_runs_after_every_weekly_job_that_writes() -> None:
    """Review R2-F1 (M3): the 120-day announcement retention and the 400 MB check run every week (BRIEF §2.8), after
    the jobs that write, also when one of them failed."""
    doc = yaml.safe_load((WF / "weekly.yml").read_text(encoding="utf-8"))
    job = doc["jobs"]["size_guard"]
    writers = set(doc["jobs"]) - {"check", "size_guard"}
    assert writers and set(job["needs"]) == writers | {"check"}
    assert job["if"].startswith("always()") and "needs.check.outputs.db == 'true'" in job["if"]
    runs = [r for r in steps("weekly.yml", "size_guard") if "python -m pipeline" in r]
    assert "pipeline.db.migrate" in runs[0] and runs[-1].endswith("python -m pipeline.db.size_guard")

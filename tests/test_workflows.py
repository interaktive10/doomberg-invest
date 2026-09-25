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
    for name, jobs in (
        ("daily.yml", ("us", "india", "text")),
        ("weekly.yml", ("us", "india", "capex", "scores", "capex_brief")),
        ("quarterly.yml", ("us",)),
        ("lab.yml", ("lab",)),
        ("weights.yml", ("weights",)),
    ):
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


def test_quarterly_dispatches_the_lab_after_the_universe_rebuild() -> None:
    """M8 review R1-F5: §2.1 "quarterly: ... Signal Lab re-run" (§11.8): quarterly.yml dispatches lab.yml once the
    13F step and the universe rebuild are done."""
    doc = yaml.safe_load((WF / "quarterly.yml").read_text(encoding="utf-8"))
    lab = doc["jobs"]["lab"]
    assert lab["needs"] == "us" and lab["permissions"] == {"actions": "write"}
    assert "actions" not in doc["permissions"]  # only the dispatching job's token can (least privilege)
    assert any("gh workflow run lab.yml" in str(s.get("run", "")) for s in lab["steps"])
    runs = steps("quarterly.yml", "us")
    assert "pipeline.db.seed" in runs[-1]  # the rebuild is the us job's last step, so the Lab runs on the new universe


def test_text_facts_run_daily_after_the_event_jobs_within_the_minutes_budget() -> None:
    """M5 (BRIEF §2.1 daily "capex-desk filings -> text facts", §2.5 budget): the text job follows the SEC and NSE
    event jobs (P-07 reads their announcements), has the free-tier keys, and stops starting documents at 4 minutes, so
    daily.yml stays within §2.5's ~8 minutes (M5 review R1-F8; docs/SPEC_ISSUES.md 29)."""
    doc = yaml.safe_load((WF / "daily.yml").read_text(encoding="utf-8"))
    job = doc["jobs"]["text"]
    assert set(job["needs"]) == {"check", "us", "india"} and job["if"].startswith("always()")
    assert {"GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"} <= set(job["env"])
    assert "ANTHROPIC_API_KEY" not in job["env"] and "OPENAI_API_KEY" not in job["env"]
    run = steps("daily.yml", "text")[-1]
    assert "python -m pipeline.facts.run" in run and "--minutes 4" in run


def test_the_capex_index_runs_before_scores_and_the_brief_after() -> None:
    """M5 (BRIEF §4.11): S11 reads this week's demand index and memberships; the brief lists this week's S11."""
    doc = yaml.safe_load((WF / "weekly.yml").read_text(encoding="utf-8"))
    jobs = doc["jobs"]
    assert "capex" in jobs["scores"]["needs"] and jobs["capex_brief"]["needs"] == ["check", "scores"]
    assert steps("weekly.yml", "capex")[-1].endswith("pipeline.capex.run --stage index")
    assert steps("weekly.yml", "capex_brief")[-1].endswith("pipeline.capex.run --stage brief")
    assert "needs.scores.result == 'success'" in jobs["capex_brief"]["if"]


def test_cassettes_are_recorded_by_hand_into_a_pr() -> None:
    """BRIEF §2.5 record-cassettes.yml (manual) and CLAUDE.md "never hand-edit cassettes": the workflow records with
    the free-tier keys and opens a PR touching only pipeline/llm/cassettes."""
    doc = yaml.safe_load((WF / "record-cassettes.yml").read_text(encoding="utf-8"))
    assert set(doc[True]) == {"workflow_dispatch"}  # yaml reads the `on:` key as True
    runs = "\n".join(steps("record-cassettes.yml", "record"))
    assert "python -m pipeline.facts.evaluate --record" in runs and "git add pipeline/llm/cassettes\n" in runs
    assert "gh pr create" in runs and "git add -A" not in runs and "git add ." not in runs


def test_weights_approval_runs_when_weights_change_on_main() -> None:
    """M8 review R2-F3: a push to main that changes config/weights.yaml (a merged human-approved PR) records and
    approves its version at merge time, from main only; the weekly scores run records it too before it writes a
    score (tests/db/test_lab_run.py)."""
    doc = yaml.safe_load((WF / "weights.yml").read_text(encoding="utf-8"))
    on = doc[True]  # PyYAML reads the `on:` key as the boolean True
    assert on["push"] == {"branches": ["main"], "paths": ["config/weights.yaml"]}
    job = doc["jobs"]["weights"]
    assert "github.ref == 'refs/heads/main'" in job["if"] and doc["permissions"] == {"contents": "read"}
    runs = [r for r in steps("weights.yml", "weights") if "python -m pipeline" in r]
    assert runs[0].endswith("python -m pipeline.db.migrate") and runs[-1].endswith("python -m pipeline.db.weights")

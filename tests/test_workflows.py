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
        ("weekly.yml", ("us", "india", "capex", "scores", "capex_brief", "thesis")),
        ("thesis-ingest.yml", ("ingest",)),
        ("thesis-fallback.yml", ("fallback",)),
        ("quarterly.yml", ("us",)),
        ("lab.yml", ("lab",)),
        ("weights.yml", ("weights",)),
        ("backfill.yml", ("us",)),
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


def test_the_us_weekly_job_has_room_for_a_full_quarterize() -> None:
    """The first live run (2026-09-29) quarterized all 5,884 companies in 53 minutes against a 60-minute limit. A full
    run comes back whenever the companyfacts state isn't restored (a cache miss, --force), and a run that times out
    never saves the state, so every later run would time out too."""
    doc = yaml.safe_load((WF / "weekly.yml").read_text(encoding="utf-8"))
    assert doc["jobs"]["us"]["timeout-minutes"] >= 120


def test_the_scores_job_has_room_for_its_network_stages() -> None:
    """The scores run is one transaction, so a run cut off by the limit keeps nothing and the next one starts over.
    The first live run (2026-09-29) spent the job's 40 minutes without finishing."""
    doc = yaml.safe_load((WF / "weekly.yml").read_text(encoding="utf-8"))
    assert doc["jobs"]["scores"]["timeout-minutes"] >= 90


def test_the_scores_job_gets_the_twelvedata_key() -> None:
    """US prices come from Twelve Data since 2026-10 (pipeline/net/twelvedata.py); only the scores job asks it."""
    doc = yaml.safe_load((WF / "weekly.yml").read_text(encoding="utf-8"))
    assert doc["jobs"]["scores"]["env"]["TWELVEDATA_API_KEY"] == "${{ secrets.TWELVEDATA_API_KEY }}"
    others = [job for name, job in doc["jobs"].items() if name != "scores"]
    assert all("TWELVEDATA_API_KEY" not in (job.get("env") or {}) for job in others)


def test_quarterly_dispatches_the_lab_after_the_universe_rebuild() -> None:
    """M8 review R1-F5: §2.1 "quarterly: ... Signal Lab re-run" (§11.8): quarterly.yml dispatches lab.yml once the
    13F step and the universe rebuild are done."""
    doc = yaml.safe_load((WF / "quarterly.yml").read_text(encoding="utf-8"))
    lab = doc["jobs"]["lab"]
    assert lab["needs"] == "us" and lab["permissions"] == {"actions": "write"}
    assert "actions" not in doc["permissions"]  # only the dispatching job's token can (least privilege)
    assert any("gh workflow run lab.yml" in str(s.get("run", "")) for s in lab["steps"])
    # the branch is named: gh can't look up the default branch with an actions-only token (first live run, 2026-09-29)
    assert any("--ref" in str(s.get("run", "")) for s in lab["steps"] if "gh workflow run" in str(s.get("run", "")))
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


def test_the_weekly_thesis_job_evaluates_then_queues() -> None:
    """M6 (BRIEF §4.9 step 1): kill criteria see this week's rows, then the queue is written and committed to main
    for the Sunday routine."""
    doc = yaml.safe_load((WF / "weekly.yml").read_text(encoding="utf-8"))
    job = doc["jobs"]["thesis"]
    assert set(job["needs"]) == {"check", "scores", "capex_brief"} and "needs.scores.result == 'success'" in job["if"]
    assert job["permissions"] == {"contents": "write"}
    runs = [r for r in steps("weekly.yml", "thesis") if r]
    keys = ("pipeline.thesis.kill_criteria", "pipeline.thesis.queue", "git push origin HEAD:refs/heads/main")
    order = [next(i for i, r in enumerate(runs) if key in r) for key in keys]
    assert order == sorted(order)


def test_the_queue_commit_is_main_only_and_stages_the_queue_alone() -> None:
    """M6 review R1-F5 (queue_commit): the commit step runs only on refs/heads/main, stages data/thesis_queue/ alone,
    and pushes on top of a freshly fetched origin/main, rebasing and retrying when main moved."""
    doc = yaml.safe_load((WF / "weekly.yml").read_text(encoding="utf-8"))
    step = next(s for s in doc["jobs"]["thesis"]["steps"] if "git push" in str(s.get("run", "")))
    run = step["run"]
    assert step["if"] == "github.ref == 'refs/heads/main'"
    assert "git add -- data/thesis_queue" in run and "git add -A" not in run and "git add ." not in run
    assert 'git commit -m "Thesis queue $(date -u +%G-W%V)" -- data/thesis_queue' in run
    fetch, rebase, push = (run.index(x) for x in ("git fetch --no-tags origin main", "git rebase --autostash "
                                                   "origin/main", "git push origin HEAD:refs/heads/main"))  # fmt: skip
    assert fetch < rebase < push and "for attempt in 1 2 3" in run


def test_the_digest_always_runs() -> None:
    """M6 review R1-F6 (digest_always): the digest is its own job, run every week whatever scores, the thesis job
    or the queue push did (those are the weeks source health matters)."""
    doc = yaml.safe_load((WF / "weekly.yml").read_text(encoding="utf-8"))
    job = doc["jobs"]["digest"]
    assert job["if"] == "always() && needs.check.outputs.db == 'true'"
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    assert steps("weekly.yml", "digest")[-1].endswith("python -m pipeline.digest.weekly")
    assert not any("pipeline.digest" in r for r in steps("weekly.yml", "thesis"))


def test_the_digest_links_to_the_app_without_a_repository_variable() -> None:
    """The 2026-W40 digest had no company links: APP_URL came only from a repository variable nobody had set."""
    doc = yaml.safe_load((WF / "weekly.yml").read_text(encoding="utf-8"))
    assert doc["jobs"]["digest"]["env"]["APP_URL"] == "${{ vars.APP_URL || 'https://doomberg-invest.vercel.app' }}"


def test_cards_are_ingested_on_push_and_the_fallback_runs_monday_morning() -> None:
    ingest_doc = yaml.safe_load((WF / "thesis-ingest.yml").read_text(encoding="utf-8"))
    assert ingest_doc[True]["push"]["paths"] == ["data/thesis_cards/**"]
    assert '--changed "$RUNNER_TEMP/changed.txt"' in steps("thesis-ingest.yml", "ingest")[-1]
    # M6 review R1-F4: main's code and queue; only the pushed cards come from the pushed commit
    checkout = ingest_doc["jobs"]["ingest"]["steps"][0]
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert 'git checkout "$SHA" -- data/thesis_cards' in "\n".join(steps("thesis-ingest.yml", "ingest"))
    fallback = yaml.safe_load((WF / "thesis-fallback.yml").read_text(encoding="utf-8"))
    assert fallback[True]["schedule"] == [{"cron": "0 6 * * 1"}]  # BRIEF §2.5
    assert steps("thesis-fallback.yml", "fallback")[-1].endswith("python -m pipeline.thesis.fallback_writer")


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


def test_the_web_job_migrates_and_seeds_before_the_e2e_suite() -> None:
    """M7: Playwright runs against the repo's own schema and seed on a local Supabase stack, and verify reads its
    report afterwards (even when a test failed)."""
    runs = steps("web.yml", "web")
    keys = ("pnpm typecheck", "pnpm test", "supabase start", "pipeline.db.migrate", "seed_e2e.py", "notify pgrst",
            "pnpm build", "pnpm e2e", "--only M7-")  # fmt: skip
    order = [next(i for i, r in enumerate(runs) if k in r) for k in keys]
    assert order == sorted(order)
    doc = yaml.safe_load((WF / "web.yml").read_text(encoding="utf-8"))
    verify = next(s for s in doc["jobs"]["web"]["steps"] if "--only M7-" in str(s.get("run", "")))
    assert verify.get("if") == "always()"


def test_the_web_job_runs_when_a_file_its_tests_pin_changes() -> None:
    """M7 review R1-F14: the web job's parity tests read these files, so a PR that changes one runs them."""
    doc = yaml.safe_load((WF / "web.yml").read_text(encoding="utf-8"))
    pinned = ("config/staleness.yaml", "pipeline/screener.py", "docs/BRIEF.md", "config/signals.yaml",
              "pipeline/signals/weekly.py", "pipeline/signals/s01_orderbook.py", "pipeline/thesis/evidence_pack.py",
              "config/guards.yaml")  # fmt: skip
    for trigger in ("pull_request", "push"):
        paths = doc[True][trigger]["paths"]
        assert all(p in paths for p in pinned), (trigger, [p for p in pinned if p not in paths])


def test_the_supabase_cli_is_pinned_to_the_version_in_docs() -> None:
    """M7 review R1-F15 (BRIEF §2.2 pin versions): web.yml installs one Supabase CLI release, the one docs/VERSIONS.md
    names, so the local stack's images and `supabase status` output don't change under the job."""
    import re

    doc = yaml.safe_load((WF / "web.yml").read_text(encoding="utf-8"))
    step = next(s for s in doc["jobs"]["web"]["steps"] if str(s.get("uses", "")).startswith("supabase/setup-cli"))
    version = str(step["with"]["version"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    versions = (WF.parents[1] / "docs" / "VERSIONS.md").read_text(encoding="utf-8")
    assert f"| Supabase CLI (web.yml's local stack) | {version} " in versions

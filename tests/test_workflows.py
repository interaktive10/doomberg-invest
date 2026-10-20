"""Scheduled workflows (BRIEF §2.5): step order that the pipeline depends on, and the triggers and jobs that keep the
monthly Actions minutes in budget (the 2026-10 overhaul, PR 1)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows"
LLM_KEYS = {"GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"}


def load(name: str) -> dict[Any, Any]:
    doc: dict[Any, Any] = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
    return doc


def steps(name: str, job: str) -> list[str]:
    return [str(s.get("run", "")) for s in load(name)["jobs"][job]["steps"]]


def step(name: str, job: str, key: str) -> tuple[int, dict[str, Any]]:
    """The first step of `job` whose run (or uses) contains `key`, with its index."""
    return next(
        (i, s)
        for i, s in enumerate(load(name)["jobs"][job]["steps"])
        if key in str(s.get("run", "")) or key in str(s.get("uses", ""))
    )


def test_13f_runs_before_the_universe_re_seed() -> None:
    """Review F9 (M2): the re-seed puts every listed filer back in the universe until the next weekly run, so 13F
    must map CUSIPs before it."""
    runs = steps("quarterly.yml", "us")
    thirteen_f = next(i for i, r in enumerate(runs) if "pipeline.us.quarterly" in r)
    seed = next(i for i, r in enumerate(runs) if "pipeline.db.seed" in r)
    assert thirteen_f < seed


def test_every_pipeline_job_migrates_first() -> None:
    for name, jobs in (
        ("daily.yml", ("us",)),
        ("weekly.yml", ("us", "scores", "publish")),
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
    the jobs that write, also when one of them failed. The guard is publish's last step; publish needs every other
    weekly job."""
    jobs = load("weekly.yml")["jobs"]
    assert set(jobs) == {"us", "scores", "publish"}
    assert set(jobs["publish"]["needs"]) == set(jobs) - {"publish"} and jobs["publish"]["if"] == "${{ !cancelled() }}"
    runs = [r for r in steps("weekly.yml", "publish") if "python -m pipeline" in r]
    assert "pipeline.db.migrate" in runs[0] and runs[-1].endswith("python -m pipeline.db.size_guard")


def test_the_us_weekly_job_has_room_for_a_full_quarterize() -> None:
    """The first live run (2026-09-29) quarterized all 5,884 companies in 53 minutes against a 60-minute limit. A full
    run comes back whenever the companyfacts state isn't restored (a cache miss, --force), and a run that times out
    never saves the state, so every later run would time out too."""
    assert load("weekly.yml")["jobs"]["us"]["timeout-minutes"] >= 120


def test_the_scores_job_has_room_for_its_network_stages() -> None:
    """The scores run is one transaction, so a run cut off by the limit keeps nothing and the next one starts over.
    The first live run (2026-09-29) spent the job's 40 minutes without finishing."""
    assert load("weekly.yml")["jobs"]["scores"]["timeout-minutes"] >= 90


def test_the_scores_job_gets_the_twelvedata_key() -> None:
    """US prices come from Twelve Data since 2026-10 (pipeline/net/twelvedata.py); only the scores job asks it."""
    jobs = load("weekly.yml")["jobs"]
    assert jobs["scores"]["env"]["TWELVEDATA_API_KEY"] == "${{ secrets.TWELVEDATA_API_KEY }}"
    others = [job for name, job in jobs.items() if name != "scores"]
    assert all("TWELVEDATA_API_KEY" not in (job.get("env") or {}) for job in others)
    assert all("TWELVEDATA_API_KEY" not in (s.get("env") or {}) for job in others for s in job["steps"])


def test_scores_run_only_after_a_us_run_that_succeeded_and_score_the_us_alone() -> None:
    """Overhaul PR 1: India is paused (docs/SPEC_ISSUES.md 46), so a week without fresh US data has nothing to score.
    `us` skips its steps without the secrets and still succeeds, so scores also need it to have run."""
    jobs = load("weekly.yml")["jobs"]
    scores = jobs["scores"]
    assert scores["needs"] == "us"
    assert scores["if"] == "needs.us.result == 'success' && needs.us.outputs.ran == 'true'"
    assert jobs["us"]["outputs"]["ran"] == "${{ steps.secrets.outputs.ok }}"
    assert steps("weekly.yml", "scores")[-1].endswith("python -m pipeline.signals.weekly --markets us")


def test_quarterly_dispatches_the_lab_after_the_universe_rebuild() -> None:
    """M8 review R1-F5: §2.1 "quarterly: ... Signal Lab re-run" (§11.8): quarterly.yml dispatches lab.yml once the
    13F step and the universe rebuild are done (not when `us` skipped them for want of a secret)."""
    doc = load("quarterly.yml")
    lab = doc["jobs"]["lab"]
    assert lab["needs"] == "us" and lab["permissions"] == {"actions": "write"}
    assert lab["if"] == "needs.us.outputs.ran == 'true'"
    assert "actions" not in doc["permissions"]  # only the dispatching job's token can (least privilege)
    assert any("gh workflow run lab.yml" in str(s.get("run", "")) for s in lab["steps"])
    # the branch is named: gh can't look up the default branch with an actions-only token (first live run, 2026-09-29)
    assert any("--ref" in str(s.get("run", "")) for s in lab["steps"] if "gh workflow run" in str(s.get("run", "")))
    runs = steps("quarterly.yml", "us")
    assert "pipeline.db.seed" in runs[-1]  # the rebuild is the us job's last step, so the Lab runs on the new universe


def test_text_facts_run_daily_after_the_sec_step_within_the_minutes_budget() -> None:
    """M5 (BRIEF §2.1 daily "capex-desk filings -> text facts", §2.5 budget): the text step follows the SEC events
    step in the same job, has the free-tier keys, and stops starting documents at 4 minutes, so daily.yml stays
    within §2.5's ~8 minutes (M5 review R1-F8; docs/SPEC_ISSUES.md 29)."""
    sec, _ = step("daily.yml", "us", "python -m pipeline.us.daily")
    text, job = step("daily.yml", "us", "python -m pipeline.facts.run")
    assert sec < text and "--minutes 4" in job["run"]
    assert set(job["env"]) == LLM_KEYS
    assert "ANTHROPIC_API_KEY" not in job["env"] and "OPENAI_API_KEY" not in job["env"]


def test_daily_is_one_job_that_saves_its_state_right_after_the_sec_step() -> None:
    """Overhaul PR 1: SEC then text in one job. actions/cache saves only when the whole job succeeds, so the state is
    restored and saved by hand, the save right after the SEC step and also when it failed; the LLM keys are in the
    text step alone; the limit leaves room to catch up after an outage."""
    doc = load("daily.yml")
    assert list(doc["jobs"]) == ["us"]
    job = doc["jobs"]["us"]
    assert job["timeout-minutes"] >= 30
    restore, restore_step = step("daily.yml", "us", "actions/cache/restore@v4")
    sec, _ = step("daily.yml", "us", "python -m pipeline.us.daily")
    save, save_step = step("daily.yml", "us", "actions/cache/save@v4")
    assert restore < sec and save == sec + 1 and save_step["if"].startswith("always()")
    assert save_step["with"]["path"] == restore_step["with"]["path"]
    assert save_step["with"]["key"] == restore_step["with"]["key"]
    assert "daily_state.json" in save_step["with"]["path"]
    assert not any(str(s.get("uses", "")).startswith("actions/cache@") for s in job["steps"])
    text, _ = step("daily.yml", "us", "python -m pipeline.facts.run")
    assert not LLM_KEYS & set(job.get("env") or {})
    assert all(not LLM_KEYS & set(s.get("env") or {}) for i, s in enumerate(job["steps"]) if i != text)


def test_cassettes_are_recorded_by_hand_into_a_pr() -> None:
    """BRIEF §2.5 record-cassettes.yml (manual) and CLAUDE.md "never hand-edit cassettes": the workflow records with
    the free-tier keys and opens a PR touching only pipeline/llm/cassettes."""
    doc = load("record-cassettes.yml")
    assert set(doc[True]) == {"workflow_dispatch"}  # yaml reads the `on:` key as True
    runs = "\n".join(steps("record-cassettes.yml", "record"))
    assert "python -m pipeline.facts.evaluate --record" in runs and "git add pipeline/llm/cassettes\n" in runs
    assert "gh pr create" in runs and "git add -A" not in runs and "git add ." not in runs


def test_the_weekly_publish_job_evaluates_then_queues() -> None:
    """M6 (BRIEF §4.9 step 1): kill criteria see this week's rows, then the queue is written and committed to main
    for the Sunday routine; then the digest and the storage guard."""
    doc = load("weekly.yml")
    assert doc["jobs"]["publish"]["permissions"] == {"contents": "write", "issues": "write"}
    assert doc["permissions"] == {"contents": "read"}  # the other jobs' tokens can't write
    runs = [r for r in steps("weekly.yml", "publish") if r]
    keys = ("pipeline.thesis.kill_criteria", "pipeline.thesis.queue", "git push origin HEAD:refs/heads/main",
            "pipeline.digest.weekly", "pipeline.db.size_guard")  # fmt: skip
    order = [next(i for i, r in enumerate(runs) if key in r) for key in keys]
    assert order == sorted(order)


def test_the_queue_needs_this_weeks_scores_while_the_digest_and_guard_run_regardless() -> None:
    """Overhaul PR 1 (publish = thesis + digest + size_guard): the kill-criteria, queue and commit steps run only
    after this week's scores; the digest and the storage guard run on !cancelled(), also after an earlier step
    failed, each with its own limit so that a hung step can't time out the job and cancel them."""
    publish = load("weekly.yml")["jobs"]["publish"]
    for key in ("pipeline.thesis.kill_criteria", "pipeline.thesis.queue", "git push origin HEAD:refs/heads/main"):
        _, s = step("weekly.yml", "publish", key)
        assert "needs.scores.result == 'success'" in s["if"] and "cancelled()" not in s["if"], key
        assert "always()" not in s["if"], key
    for key in ("pipeline.digest.weekly", "pipeline.db.size_guard"):
        _, s = step("weekly.yml", "publish", key)
        assert s["if"] == "${{ !cancelled() && steps.secrets.outputs.ok == 'true' }}", key
    work = [s for s in publish["steps"] if "python -m pipeline" in str(s.get("run", "")) and "migrate" not in s["run"]]
    assert len(work) == 4 and all(s["timeout-minutes"] for s in work)
    total = sum(s["timeout-minutes"] for s in publish["steps"] if "timeout-minutes" in s)
    assert total < publish["timeout-minutes"]


def test_the_queue_commit_is_main_only_and_stages_the_queue_alone() -> None:
    """M6 review R1-F5 (queue_commit): the commit step runs only on refs/heads/main, stages data/thesis_queue/ alone,
    and pushes on top of a freshly fetched origin/main, rebasing and retrying when main moved."""
    _, s = step("weekly.yml", "publish", "git push")
    run = s["run"]
    assert s["if"] == "needs.scores.result == 'success' && github.ref == 'refs/heads/main'"
    assert "git add -- data/thesis_queue" in run and "git add -A" not in run and "git add ." not in run
    assert 'git commit -m "Thesis queue $(date -u +%G-W%V)" -- data/thesis_queue' in run
    fetch, rebase, push = (run.index(x) for x in ("git fetch --no-tags origin main", "git rebase --autostash "
                                                   "origin/main", "git push origin HEAD:refs/heads/main"))  # fmt: skip
    assert fetch < rebase < push and "for attempt in 1 2 3" in run


def test_the_digest_always_runs() -> None:
    """M6 review R1-F6 (digest_always): the digest runs every week whatever scores, the kill criteria, the queue or
    its push did (those are the weeks source health matters); only a cancelled run skips it."""
    publish = load("weekly.yml")["jobs"]["publish"]
    assert publish["if"] == "${{ !cancelled() }}"
    _, s = step("weekly.yml", "publish", "python -m pipeline.digest.weekly")
    assert "!cancelled()" in s["if"] and "needs.scores" not in s["if"]
    assert s["run"].endswith("python -m pipeline.digest.weekly")


def test_the_digest_links_to_the_app_without_a_repository_variable() -> None:
    """The 2026-W40 digest had no company links: APP_URL came only from a repository variable nobody had set. Env is
    set per step in publish: the token and the app URL reach the digest step alone."""
    publish = load("weekly.yml")["jobs"]["publish"]
    i, s = step("weekly.yml", "publish", "python -m pipeline.digest.weekly")
    assert s["env"]["APP_URL"] == "${{ vars.APP_URL || 'https://doomberg-invest.vercel.app' }}"
    assert s["env"]["GITHUB_TOKEN"] == "${{ github.token }}"
    assert "env" not in publish
    others = [o for j, o in enumerate(publish["steps"]) if j != i]
    assert all(not {"APP_URL", "GITHUB_TOKEN"} & set(o.get("env") or {}) for o in others)
    assert all("DATABASE_URL" in o["env"] for o in others if "python -m pipeline" in str(o.get("run", "")))


def test_the_digest_is_told_why_a_week_has_no_scores() -> None:
    """Overhaul PR 1 review (actions-GHA-1): scores run only after a us job that ran and succeeded; the digest step
    gets both jobs' results (pipeline.digest.weekly.unscored_why) to say which one stopped the week's scores."""
    import inspect

    from pipeline.digest.weekly import unscored_why

    doc = load("weekly.yml")
    _, s = step("weekly.yml", "publish", "python -m pipeline.digest.weekly")
    names = ("US_RESULT", "US_RAN", "SCORES_RESULT")
    assert {k: v for k, v in s["env"].items() if k in names} == {
        "US_RESULT": "${{ needs.us.result }}",
        "US_RAN": "${{ needs.us.outputs.ran }}",
        "SCORES_RESULT": "${{ needs.scores.result }}",
    }
    assert doc["jobs"]["publish"]["needs"] == ["us", "scores"] and "ran" in doc["jobs"]["us"]["outputs"]
    assert all(f'"{k}"' in inspect.getsource(unscored_why) for k in names)  # the names the digest reads


def test_cards_are_ingested_on_push_and_the_fallback_runs_monday_morning() -> None:
    ingest_doc = load("thesis-ingest.yml")
    assert ingest_doc[True]["push"]["paths"] == ["data/thesis_cards/**"]
    assert '--changed "$RUNNER_TEMP/changed.txt"' in steps("thesis-ingest.yml", "ingest")[-1]
    # M6 review R1-F4: main's code and queue; only the pushed cards come from the pushed commit
    checkout = ingest_doc["jobs"]["ingest"]["steps"][0]
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert 'git checkout "$SHA" -- data/thesis_cards' in "\n".join(steps("thesis-ingest.yml", "ingest"))
    fallback = load("thesis-fallback.yml")
    assert fallback[True]["schedule"] == [{"cron": "0 6 * * 1"}]  # BRIEF §2.5
    assert steps("thesis-fallback.yml", "fallback")[-1].endswith("python -m pipeline.thesis.fallback_writer")


def test_weights_approval_runs_when_weights_change_on_main() -> None:
    """M8 review R2-F3: a push to main that changes config/weights.yaml (a merged human-approved PR) records and
    approves its version at merge time, from main only; the weekly scores run records it too before it writes a
    score (tests/db/test_lab_run.py)."""
    doc = load("weights.yml")
    on = doc[True]  # PyYAML reads the `on:` key as the boolean True
    assert on["push"] == {"branches": ["main"], "paths": ["config/weights.yaml"]}
    job = doc["jobs"]["weights"]
    assert "github.ref == 'refs/heads/main'" in job["if"] and doc["permissions"] == {"contents": "read"}
    runs = [r for r in steps("weights.yml", "weights") if "python -m pipeline" in r]
    assert runs[0].endswith("python -m pipeline.db.migrate") and runs[-1].endswith("python -m pipeline.db.weights")


def test_no_workflow_has_a_check_job() -> None:
    """Overhaul PR 1: a `check` job cost a runner start (a billed minute) per run. Each pipeline job checks its
    secrets in its first step instead and skips the steps after it; a missing secret is a notice, never a failure.
    DATABASE_URL is needed everywhere, SEC_USER_AGENT for US work."""
    for path in sorted(WF.glob("*.yml")):
        assert "check" not in load(path.name)["jobs"], path.name
    for name, job, secrets in (
        ("daily.yml", "us", ("DATABASE_URL", "SEC_USER_AGENT")),
        ("weekly.yml", "us", ("DATABASE_URL", "SEC_USER_AGENT")),
        ("weekly.yml", "publish", ("DATABASE_URL",)),
        ("quarterly.yml", "us", ("DATABASE_URL", "SEC_USER_AGENT")),
        ("weights.yml", "weights", ("DATABASE_URL",)),
    ):
        first, *rest = load(name)["jobs"][job]["steps"]
        assert first["id"] == "secrets" and all(f'"${secret}"' in first["run"] for secret in secrets), (name, job)
        assert "::notice::" in first["run"] and "exit 1" not in first["run"] and "::error::" not in first["run"]
        gated = ("steps.secrets.outputs.ok == 'true'", "needs.scores.result == 'success'")
        assert all(any(g in s.get("if", "") for g in gated) for s in rest), (name, job)


def test_india_is_paused() -> None:
    """Overhaul PR 1 (docs/SPEC_ISSUES.md 46): no India job runs on a schedule; pipeline/india and its rows stay."""
    for path in sorted(WF.glob("*.yml")):
        jobs = load(path.name)["jobs"]
        assert not [j for j in jobs if "india" in j], path.name
        runs = [str(s.get("run", "")) for job in jobs.values() for s in job.get("steps", [])]
        assert not [r for r in runs if "pipeline.india" in r], path.name


def test_every_job_runs_on_a_pinned_runner() -> None:
    """Overhaul PR 1: ubuntu-latest moves to a new image on GitHub's schedule; a pinned image changes only in a PR."""
    for path in sorted(WF.glob("*.yml")):
        for name, job in load(path.name)["jobs"].items():
            assert job["runs-on"] == "ubuntu-24.04", (path.name, name)


def test_the_universe_workflow_is_gone() -> None:
    """Overhaul PR 1: the snapshots it committed are in the repo, and the quarterly run fetches a fresh SEC listing on
    its own runner."""
    assert not (WF / "universe.yml").exists()


def test_ci_runs_on_pull_requests_without_label_events() -> None:
    """Overhaul PR 1: no run on a push to main (the PR's run tested the merged code) and none when a label changes
    (protected.yml re-checks labels alone); verify-m8's M0-01 is the whole test suite, so no separate `make test`."""
    doc = load("ci.yml")
    assert doc[True] == {"pull_request": {"types": ["opened", "synchronize", "reopened", "ready_for_review"]}}
    assert set(doc["jobs"]) == {"python"}
    runs = steps("ci.yml", "python")
    assert "make verify-m8" in runs and not any("make test" in r or "pytest" in r for r in runs)
    assert {"make lint", "make type", "make guard"} <= set(runs)


def test_the_protected_check_reruns_when_a_label_changes() -> None:
    """BRIEF Appendix D: adding or removing human-approved re-runs the `protected` job (the required check's name)
    in its own workflow, without the Python job."""
    doc = load("protected.yml")
    types = doc[True]["pull_request"]["types"]
    assert set(doc[True]) == {"pull_request"}
    assert {"opened", "synchronize", "reopened", "labeled", "unlabeled"} <= set(types)
    assert list(doc["jobs"]) == ["protected"] and "name" not in doc["jobs"]["protected"]
    checkout = doc["jobs"]["protected"]["steps"][0]
    assert checkout["uses"] == "actions/checkout@v4" and checkout["with"]["fetch-depth"] == 0
    run = steps("protected.yml", "protected")[-1]
    assert run.startswith("python3 scripts/protected_check.py --base") and '--labels "${LABELS}"' in run


def test_the_web_job_migrates_and_seeds_before_the_e2e_suite() -> None:
    """M7: Playwright runs against the repo's own schema and seed on a local Supabase stack, and verify reads its
    report afterwards (even when a test failed)."""
    runs = steps("web.yml", "web")
    keys = ("pnpm typecheck", "pnpm test", "supabase start", "pipeline.db.migrate", "seed_e2e.py", "notify pgrst",
            "pnpm build", "pnpm e2e", "--only M7-")  # fmt: skip
    order = [next(i for i, r in enumerate(runs) if k in r) for k in keys]
    assert order == sorted(order)
    _, verify = step("web.yml", "web", "--only M7-")
    assert verify.get("if") == "always() && steps.changes.outputs.e2e == 'true'"


def test_the_web_job_runs_when_a_file_its_tests_pin_changes() -> None:
    """M7 review R1-F14: the web job's parity tests read these files, so a PR that changes one runs them."""
    doc = load("web.yml")
    pinned = ("config/staleness.yaml", "pipeline/screener.py", "docs/BRIEF.md", "config/signals.yaml",
              "pipeline/signals/weekly.py", "pipeline/signals/s01_orderbook.py", "pipeline/thesis/evidence_pack.py",
              "config/guards.yaml")  # fmt: skip
    paths = doc[True]["pull_request"]["paths"]
    assert all(p in paths for p in pinned), [p for p in pinned if p not in paths]


def test_web_runs_on_pull_requests_and_gates_the_e2e_steps() -> None:
    """Overhaul PR 1: no run on a push to main. The type check and Vitest run on every web.yml trigger; Supabase, the
    build and Playwright only when the PR changes the app, the schema, Supabase, the e2e scripts or web.yml."""
    doc = load("web.yml")
    assert set(doc[True]) == {"pull_request"}
    gate = "steps.changes.outputs.e2e == 'true'"
    job = doc["jobs"]["web"]
    assert job["steps"][0]["with"]["fetch-depth"] == 2  # HEAD^1, the base tip, for the diff
    changes, s = step("web.yml", "web", "git diff --name-only --no-renames HEAD^1 HEAD")
    assert s["id"] == "changes"  # --no-renames: a file moved out of web/ or db/migrations/ lists its old path too
    pattern = re.search(r"grep -qE '([^']+)'", s["run"])
    assert pattern is not None
    e2e = re.compile(pattern.group(1))
    gated = ("web/app/page.tsx", "db/migrations/0016_x.sql", "supabase/config.toml", "scripts/seed_e2e.py",
             "scripts/e2e_report.py", ".github/workflows/web.yml")  # fmt: skip
    ungated = ("config/staleness.yaml", "docs/BRIEF.md", "scripts/verify.py", "pipeline/screener.py",
               "scripts/seed_e2e.py.bak", "webx/a.ts", ".github/workflows/web.yml.orig")  # fmt: skip
    assert all(e2e.search(p) for p in gated) and not any(e2e.search(p) for p in ungated)
    assert all(p in doc[True]["pull_request"]["paths"] for p in ("web/**", "db/migrations/**", "supabase/**"))
    first, _ = step("web.yml", "web", "supabase/setup-cli")
    for i, st in enumerate(job["steps"]):
        run = str(st.get("run", ""))
        if run in ("pnpm typecheck", "pnpm test"):
            assert "if" not in st and i < first, run
        elif i >= first and "upload-artifact" not in str(st.get("uses", "")):
            assert gate in st["if"], st
    assert changes < first


def test_the_supabase_cli_is_pinned_to_the_version_in_docs() -> None:
    """M7 review R1-F15 (BRIEF §2.2 pin versions): web.yml installs one Supabase CLI release, the one docs/VERSIONS.md
    names, so the local stack's images and `supabase status` output don't change under the job."""
    _, s = step("web.yml", "web", "supabase/setup-cli")
    version = str(s["with"]["version"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    versions = (WF.parents[1] / "docs" / "VERSIONS.md").read_text(encoding="utf-8")
    assert f"| Supabase CLI (web.yml's local stack) | {version} " in versions

"""Why a week has no scores (pipeline/digest/weekly.py unscored_why; overhaul PR 1 review, actions-GHA-1). weekly.yml
runs scores only after a us job that ran and succeeded, and passes the jobs' results to the digest step, so the digest
names the job that stopped the week's scores. tests/db/test_thesis.py checks the digest's line."""

from __future__ import annotations

import pytest

from pipeline.digest.weekly import UNSCORED, unscored_why


@pytest.mark.parametrize(
    ("env", "why"),
    [
        ({"US_RESULT": "failure", "US_RAN": "true", "SCORES_RESULT": "skipped"},
         "the US data run failed, so nothing was scored"),
        ({"US_RESULT": "cancelled", "US_RAN": "true", "SCORES_RESULT": "skipped"},
         "the US data run was cancelled or timed out, so nothing was scored"),
        ({"US_RESULT": "success", "US_RAN": "", "SCORES_RESULT": "skipped"},
         "the US data run skipped its steps (a secret is missing), so nothing was scored"),
        ({"US_RESULT": "success", "US_RAN": "true", "SCORES_RESULT": "failure"}, "the scoring run failed"),
        ({"US_RESULT": "success", "US_RAN": "true", "SCORES_RESULT": "cancelled"},
         "the scoring run was cancelled or timed out"),
        ({"US_RESULT": "success", "US_RAN": "true", "SCORES_RESULT": "success"},
         "the scoring run finished without writing any"),
        ({}, UNSCORED),  # a digest run by hand, outside weekly.yml
    ],
    ids=["us-failed", "us-cancelled", "us-skipped", "scores-failed", "scores-cancelled", "scores-ok", "by-hand"],
)  # fmt: skip
def test_the_reason_names_the_job_that_stopped_the_scores(env: dict[str, str], why: str) -> None:
    assert unscored_why(env) == why

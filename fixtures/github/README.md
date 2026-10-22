# fixtures/github

GitHub REST answers for the Actions minutes meter (`pipeline/digest/minutes.py`, `tests/digest/test_minutes.py`), in
the shape GitHub documents for `GET /repos/{owner}/{repo}/actions/runs` (`total_count`, `workflow_runs[]`) and
`GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs` (`total_count`, `jobs[]` with `status`, `started_at`,
`completed_at`). They are **not recordings**: written by hand, cut to the fields the meter reads, for the paging and
rounding tests, with two items a page.

- `runs_page1.json`, `runs_page2.json`: three runs since 2026-11-01.
- `jobs_101_page1.json`, `jobs_101_page2.json`: 61 s (2 minutes), 59 s (1), and a job that never started (0: the shape
  of the blocked daily run of 2026-10-20).
- `jobs_102.json`: exactly 120 s (2) and a skipped job (0).
- `jobs_103.json`: 601 s (11) in the first attempt and a second attempt still running (0).

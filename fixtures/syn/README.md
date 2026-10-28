# F-SYN (BRIEF §9, M5-01)

Twelve documents from fictional companies, each with planted facts. `scripts/make_synthetic.py` (seed 7) writes them
all, together with `ground_truth.json`. Same seed, same bytes.

| Files | What they exercise |
|---|---|
| `*_pr_*.htm` (4) | press releases (EX-99.1 style, one India announcement): the whole body is read |
| `*_10q*.htm` (4) | 10-Q-style filings: a table of contents, an inline-XBRL hidden header, MD&A, notes (revenue/RPO, leases, commitments, debt) |
| `kyst_10k_2025_risk.htm`, `kyst_10k_2026_risk.htm` | two versions of Item 1A for the risk-factor diff (`risk_changes` in the ground truth) |
| `*.pdf` (2) | investor presentations, read page by page |

`ground_truth.json` gives, for each document, its company, kind, title and publication time. Each of the 24 planted facts is listed with its type, subject key, value (scaled), unit, quote and expected Verify-1 status. The rupee order of the Indian company is in its own currency, so it expects `verified` (docs/SPEC_ISSUES.md 31 option b, 58).

Every document also carries distractors that P-01 must not return: share repurchases, dividends, EPS, stock price and analyst ratings.

M5-01 scores recall (≥ 95%) and precision (≥ 98%) on recorded free-tier answers with `python -m pipeline.facts.evaluate --replay`. `record-cassettes.yml` records those answers.

Without cassettes, `tests/facts/test_fsyn.py` runs the same corpus through an oracle provider that answers from the ground truth. That checks the engine's structure (chunking, prefilter, grounding, Verify-1, offsets), but not a model's recall. The M5-01 check then reports BLOCKED(key).

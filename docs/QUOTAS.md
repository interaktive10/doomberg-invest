# Free-tier quotas (BRIEF §2.6, §11.3)

Limits are **per project/account and change without notice**, so none are hard-coded. Fill in `config/quotas.yaml`
from each provider's own console, then note the date below. `null` means "not filled in", and the router treats that
provider as unavailable (items stay `deferred`).

| Provider | Where to read the live limits | Fields to copy into `config/quotas.yaml` | Filled on |
|---|---|---|---|
| Google AI Studio (Gemini) | aistudio.google.com → your project → rate-limit / usage page for the API key's project. Read the rows for the exact models in `providers.gemini.models` | `requests_per_minute`, `requests_per_day`, `tokens_per_day` (use tokens-per-minute × 1440 only if no daily token cap is shown) | 2026-10-08: 15 RPM, 500 RPD (gemini-3.5-flash-lite) |
| Groq | console.groq.com → Settings → Limits (per-model table) | same three, for the model in `providers.groq.models` | — |
| OpenRouter | openrouter.ai → Settings / Keys; `GET https://openrouter.ai/api/v1/key` with the key returns the key's current limit and usage. `:free` models have their own per-day cap, which depends on account credit status | `requests_per_minute`, `requests_per_day` | — |

Other settings in `config/quotas.yaml`:
- `routing`: the provider order per prompt. A 429 blocks a provider until its Retry-After (else the next UTC day), and the next one is tried.
- `work_order`: `[thesis, stage]`, for the record only: the code's order is `RANK` in `pipeline/facts/run.py` (a test keeps the two the same). The daily text run reads the documents of theses and research entries first, then those of the stage names, each newest first (`pipeline/facts/run.py`; BRIEF §4.5, docs/SPEC_ISSUES.md 50).
- `text_daily_limits.documents_per_day`: the daily text run's cap. While it is `null`, the run reads at most 40 documents a day. daily.yml also starts no document after 6 minutes (`pipeline/facts/run.py --minutes 6`), so the daily job takes about 9-10 minutes against BRIEF §2.5's 8 (docs/SPEC_ISSUES.md 50).
- `actions`: GitHub Actions minutes (`pipeline/digest/minutes.py`). Copy `cycle_day` (the day the billing cycle resets) and `other_repos` (this cycle's minutes in your other private repositories) from github.com/settings/billing. The weekly digest prints used and projected minutes, with a warning above `warn_above` (1,600 of the free 2,000); lab-prices.yml and lab.yml run only while used + their limit + `reserve` + the remaining scheduled runs (at `typical` minutes each) stays at or below `gate_max` (1,900). The digest's projection also counts the Lab download's remaining runs (lab-prices.yml: its pending tickers at 650 a run) at `download_run` minutes each (95); the gate leaves them out, since each of those runs asks for its own 120.

Today's usage is read back from `llm_calls`, so re-running a job the same day doesn't overspend a daily quota.

Rules (BRIEF §2.6):
- No credit card on any provider. Nothing can bill by accident, and exhaustion means `deferred`, never spend.
- Record the date you copied the numbers. Re-check them each quarter (§11.8) or whenever `llm_calls` shows repeated 429s.

Non-LLM sources (documented fair-use limits, enforced in `pipeline/net/http.py`):

| Source | Limit used | Basis |
|---|---|---|
| SEC EDGAR | ≤ 8 req/s, declared `SEC_USER_AGENT` | SEC fair-access policy (10 req/s max); BRIEF §2.7 |
| NSE / BSE | 1 request per 3 s, cookie warm-up | BRIEF §4.3; old Doomberg measured about 3-4/min/IP (`docs/DOOMBERG_AUDIT.md` §4) |
| Twelve Data (US weekly prices; the Signal Lab's history) | 1 request per 8 s, ≤ 400 symbols/week (one credit each, Saturday); the Lab's download (lab-prices.yml) ≤ 650 credits a run, Sunday to Thursday in November and December | free plan: 8 credits a minute, 800 a day, no card; key in `TWELVEDATA_API_KEY`; docs/SPEC_ISSUES.md 38, 51 |

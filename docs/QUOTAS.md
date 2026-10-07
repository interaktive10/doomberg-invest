# Free-tier quotas (BRIEF §2.6, §11.3)

Limits are **per project/account and change without notice**, so none are hard-coded. Fill in `config/quotas.yaml`
from each provider's own console, then note the date below. `null` means "not filled in", and the router treats that
provider as unavailable (items stay `deferred`).

| Provider | Where to read the live limits | Fields to copy into `config/quotas.yaml` | Filled on |
|---|---|---|---|
| Google AI Studio (Gemini) | aistudio.google.com → your project → rate-limit / usage page for the API key's project. Read the rows for the exact models in `providers.gemini.models` | `requests_per_minute`, `requests_per_day`, `tokens_per_day` (use tokens-per-minute × 1440 only if no daily token cap is shown) | — |
| Groq | console.groq.com → Settings → Limits (per-model table) | same three, for the model in `providers.groq.models` | — |
| OpenRouter | openrouter.ai → Settings / Keys; `GET https://openrouter.ai/api/v1/key` with the key returns the key's current limit and usage. `:free` models have their own per-day cap, which depends on account credit status | `requests_per_minute`, `requests_per_day` | — |

Other settings in `config/quotas.yaml`:
- `routing`: the provider order per prompt. A 429 blocks a provider until its Retry-After (else the next UTC day), and the next one is tried.
- `work_order`: which companies' documents are read first (capex desk, then the candidate shortlist, then the rest).
- `text_daily_limits.documents_per_day`: the daily text run's cap. While it is `null`, the run reads at most 40 documents a day. The daily job also starts no document after 8 minutes (`pipeline/facts/run.py --minutes`, BRIEF §2.5 budget).

Today's usage is read back from `llm_calls`, so re-running a job the same day doesn't overspend a daily quota.

Rules (BRIEF §2.6):
- No credit card on any provider. Nothing can bill by accident, and exhaustion means `deferred`, never spend.
- Record the date you copied the numbers. Re-check them each quarter (§11.8) or whenever `llm_calls` shows repeated 429s.

Non-LLM sources (documented fair-use limits, enforced in `pipeline/net/http.py`):

| Source | Limit used | Basis |
|---|---|---|
| SEC EDGAR | ≤ 8 req/s, declared `SEC_USER_AGENT` | SEC fair-access policy (10 req/s max); BRIEF §2.7 |
| NSE / BSE | 1 request per 3 s, cookie warm-up | BRIEF §4.3; old Doomberg measured about 3-4/min/IP (`docs/DOOMBERG_AUDIT.md` §4) |
| Twelve Data (US weekly prices) | 1 request per 8 s, ≤ 400 symbols/week (one credit each) | free plan: 8 credits a minute, 800 a day, no card; key in `TWELVEDATA_API_KEY`; docs/SPEC_ISSUES.md 38 |
| Yahoo chart endpoint (`PRICE_SOURCE=yahoo` only) | 1 request per s | unofficial; refuses GitHub's runners (HTTP 429); docs/SPEC_ISSUES.md 37, 38 |
| GDELT DOC 2.0 | 1 request per 5 s (GDELT's own limit), ≤ 100 new queries a week, candidates only | BRIEF §2.7; DECISIONS.log (M4 C4) |
| FRED / EIA | 2 req/s; EIA: one monthly series a week (planned generator additions, 5 years) | free keys; BRIEF §2.7 |

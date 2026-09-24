# Free-tier quotas (BRIEF §2.6, §11.3)

Limits are **per project/account and change without notice**, so none are hard-coded. Fill in `config/quotas.yaml`
from each provider's own console, then note the date below. `null` means "not filled in", and the router treats that
provider as unavailable (items stay `deferred`).

| Provider | Where to read the live limits | Fields to copy into `config/quotas.yaml` | Filled on |
|---|---|---|---|
| Google AI Studio (Gemini) | aistudio.google.com → your project → rate-limit / usage page for the API key's project. Read the rows for the exact models in `providers.gemini.models` | `requests_per_minute`, `requests_per_day`, `tokens_per_day` (use tokens-per-minute × 1440 only if no daily token cap is shown) | — |
| Groq | console.groq.com → Settings → Limits (per-model table) | same three, for the model in `providers.groq.models` | — |
| OpenRouter | openrouter.ai → Settings / Keys; `GET https://openrouter.ai/api/v1/key` with the key returns the key's current limit and usage. `:free` models have their own per-day cap, which depends on account credit status | `requests_per_minute`, `requests_per_day` | — |

Rules (BRIEF §2.6):
- No credit card on any provider. Nothing can bill by accident, and exhaustion means `deferred`, never spend.
- Record the date you copied the numbers. Re-check them each quarter (§11.8) or whenever `llm_calls` shows repeated 429s.

Non-LLM sources (documented fair-use limits, enforced in `pipeline/net/http.py`):

| Source | Limit used | Basis |
|---|---|---|
| SEC EDGAR | ≤ 8 req/s, declared `SEC_USER_AGENT` | SEC fair-access policy (10 req/s max); BRIEF §2.7 |
| NSE / BSE | 1 request per 3 s, cookie warm-up | BRIEF §4.3; old Doomberg measured about 3-4/min/IP (`docs/DOOMBERG_AUDIT.md` §4) |
| Stooq | 1 request per 2 s, ≤ 400 symbols/week | BRIEF §2.7 |
| GDELT DOC 2.0 | 1 req/s, candidates only | BRIEF §2.7 |
| FRED / EIA | 2 req/s | free keys; BRIEF §2.7 |

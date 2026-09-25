# Doomberg Invest web app (BRIEF §6)

Next.js 15 (App Router, server components and server actions) on Supabase, single user. The browser never talks to
Supabase directly: every read and write runs on the server with the service-role key, and the app makes no LLM calls.

## Environment (BRIEF §2.4; server-side only)

| Variable | What |
|---|---|
| `SUPABASE_URL` | the project URL |
| `SUPABASE_ANON_KEY` | the anon key (sign-in only) |
| `SUPABASE_SERVICE_ROLE_KEY` | the service-role key (data; never exposed to the browser) |
| `APP_ALLOWED_EMAIL` | the one address that may sign in |

In Supabase → Authentication:
- **URL configuration:** set the Site URL to the app's URL and add `<app URL>/auth/callback` to the redirect URLs.
- **Email templates** (Magic Link, and Confirm signup): make the link
  `{{ .SiteURL }}/auth/callback?token_hash={{ .TokenHash }}&type=email` (as `supabase/templates/*.html` do for the
  local stack). The app verifies the token on the server, so the link needs no code verifier in the browser; the
  default PKCE link (`?code=`) still works when opened in the browser that asked for it.

## Commands

- `pnpm install`, then `pnpm dev` (http://127.0.0.1:3000)
- `pnpm typecheck`, `pnpm test` (Vitest), `pnpm build`
- `pnpm e2e` (Playwright): needs `supabase start` at the repo root, the migrations
  (`uv run python -m pipeline.db.migrate --database-url <DB_URL>`), `scripts/seed_e2e.py` and `pnpm build`.
  `.github/workflows/web.yml` runs the whole sequence; `scripts/verify.py` reads its report for M7-01..M7-03.

## Deploy (Vercel Hobby or Cloudflare Pages, §2.1)

Root directory `web`, framework Next.js, the four variables above. Settings reads `../config/*.yaml`, which
`next.config.ts` traces into the deployment.

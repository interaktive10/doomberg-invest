# Versions (BRIEF §2.2)

Pinned in `uv.lock` (Python) and `web/pnpm-lock.yaml` (web, from M7). Regenerate this table when the lockfile changes.

| Component | Version |
|---|---|
| Python | 3.12 (uv-managed) |
| uv | 0.8.x |
| polars | 1.44.2 |
| httpx | 0.28.1 |
| pydantic | 2.13.5 |
| psycopg | 3.3.6 |
| pypdfium2 | 5.13.0 |
| rapidfuzz | 3.14.6 |
| scipy | 1.18.1 |
| pyyaml | 6.0.3 |
| cryptography | 50.0.2 |
| pytest | 9.1.1 |
| ruff | 0.16.8 |
| mypy | 2.3.1 |
| Node / pnpm | 22 / 9.15.9 |
| Next.js / React / TypeScript | 15.5.26 / 19.3.0 / 5.9.3 |
| Tailwind / @tailwindcss/postcss | 4.3.3 / 4.3.3 |
| shadcn/ui helpers | class-variance-authority 0.7.1, tailwind-merge 3.7.0, clsx 2.1.1, @radix-ui/react-slot 1.3.3 |
| @supabase/ssr / supabase-js / zod | 0.6.1 / 2.117.2 / 3.25.76 |
| Recharts / react-markdown / remark-gfm | 2.15.4 / 10.1.0 / 4.0.1 |
| Playwright / @axe-core/playwright / Vitest | 1.63.0 / 4.13.0 / 3.2.7 |
| Supabase CLI (web.yml's local stack) | 2.118.0 (images: postgres 17.6.1.171, gotrue v2.197.0, postgrest v16.3, kong 2.8.1, mailpit v1.30.2) |
| PostgreSQL (dev) | 16, pre-installed in cloud sessions |

The web versions are what `pnpm install` resolved from `web/package.json`'s ranges in CI on 2026-09-25 (web.yml prints
them); they are pinned once `web/pnpm-lock.yaml` is committed (SPEC_ISSUES 32).

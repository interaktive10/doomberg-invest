-- 0019: computed reports the web app reads as one row each (docs/SPEC_ISSUES.md 64): `winners` (last calendar year's
-- top gainers per market, their year so far and a backtest) and `themes` (the weekly theme pass, one row a week, its
-- own memory). Closed to the API roles like every table: the web app reads with the service role after its own check.
create table reports (
  name text not null check (name in ('winners', 'themes')),
  week_end date not null,
  body jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (name, week_end)
);
alter table reports enable row level security;

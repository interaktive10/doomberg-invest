-- 0002_access_and_pit: access control (BRIEF §3 "Access") and point-in-time columns (BRIEF §3 "Point-in-time rule").

-- ---------------------------------------------------------------- roles
-- Supabase ships anon / authenticated / service_role. Local and CI databases create them so tests run against the
-- same roles (BRIEF §8 M1-03 "local roles mirror Supabase"). On Supabase these blocks are no-ops.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end
$$;

-- ---------------------------------------------------------------- point-in-time availability
-- §3's rule says as-of reads use only rows with filed_at <= W's end, but ownership_q and corp_events have no
-- filed_at. Without one, a 13F count or an 8-K event would be visible from its quarter/event date, before anyone
-- could have read it (a look-ahead leak). Added here; see docs/SPEC_ISSUES.md 8 and docs/DECISIONS.log.
alter table ownership_q add column filed_at timestamptz not null;
alter table corp_events add column filed_at timestamptz not null;

create index insider_events_pit on insider_events (company_id, filed_at);
-- Natural keys so re-running a daily/weekly job inserts nothing twice (writers use `on conflict do nothing`).
-- value is part of the insider key: one Form 4 can carry two same-day lots of equal size at different prices.
create unique index insider_events_natural
  on insider_events (company_id, person, event_date, kind, shares, value, source_url) nulls not distinct;
create unique index corp_events_natural on corp_events (company_id, kind, event_date, source_url);
create index corp_events_pit on corp_events (company_id, filed_at);
create index ownership_q_pit on ownership_q (company_id, filed_at);
create index signal_values_week on signal_values (week_end);

-- ---------------------------------------------------------------- row-level security
-- RLS on every table with no anon/authenticated policies (§3 "Access"). Table privileges are revoked as well, so
-- an anon/authenticated query fails outright instead of returning an empty set. All access is server-side: the
-- pipeline connects as the database owner, the web app's server code as service_role.
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end
$$;

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;

grant usage on schema public to service_role;
grant select, insert, update, delete on all tables in schema public to service_role;
-- Supabase grants new tables to service_role by default; mirror that so later migrations behave the same locally.
alter default privileges in schema public grant select, insert, update, delete on tables to service_role;

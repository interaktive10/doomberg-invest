-- Review F5 (M3): one Indian insider-trading disclosure can hold two identical lines (the same person, day, shares
-- and value, e.g. two 5,000-share purchases of equal price whose holdings run 434,686 -> 439,686 -> 444,686). The
-- natural key made them one row. `line` is the line's identity within its filing (the disclosure line's XBRL
-- context); null for filings without lines (US Form 4 lots keep the old key).
alter table insider_events add column line text;
drop index insider_events_natural;
create unique index insider_events_natural
  on insider_events (company_id, person, event_date, kind, shares, value, source_url, line) nulls not distinct;

-- Review F8 (M3): NSE announcements (~4,300 a week at ~775 bytes a row with indexes) would take ~170 MB a year.
-- They are triage input (P-07, M5) and evidence for the last quarter, so they are kept 120 days
-- (pipeline/db/size_guard.py ANNOUNCEMENT_KEEP_DAYS). A function, so pipeline code never names the table in a query
-- (guard pit_rule: only pit.py reads it).
create or replace function prune_announcements(p_before date)
returns integer
language plpgsql
security invoker
set search_path = public
as $$
declare
  n integer;
begin
  delete from corp_events e where e.kind = 'announcement' and e.event_date < p_before;
  get diagnostics n = row_count;
  return n;
end
$$;

revoke all on function prune_announcements(date) from public;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on function prune_announcements(date) from anon, authenticated;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function prune_announcements(date) to service_role;
  end if;
end $$;

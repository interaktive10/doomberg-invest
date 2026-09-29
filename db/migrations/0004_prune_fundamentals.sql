-- Review F10 (M2): fundamentals_q versions that the current quarterizing code no longer produces (a code or map fix
-- re-quarterizes a company) and quarters older than the 60-quarter window (§2.8) are deleted when the company is
-- rewritten. A function, so pipeline code never names the table in a query (guard pit_rule: only pit.py reads it).
create or replace function prune_fundamentals(p_company uuid, p_keep jsonb, p_min_period date)
returns integer
language plpgsql
security invoker
set search_path = public
as $$
declare
  n integer;
begin
  delete from fundamentals_q f
   where f.company_id = p_company
     and (f.period_end < p_min_period
          or not exists (select 1 from jsonb_array_elements(p_keep) k
                          where (k->>0)::date = f.period_end and (k->>1)::timestamptz = f.filed_at));
  get diagnostics n = row_count;
  return n;
end
$$;

revoke all on function prune_fundamentals(uuid, jsonb, date) from public;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on function prune_fundamentals(uuid, jsonb, date) from anon, authenticated;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function prune_fundamentals(uuid, jsonb, date) to service_role;
  end if;
end $$;

-- Review R2-F7 (M2): a Form 4/A amends one earlier Form 4, named by its filing date (dateOfOriginalSubmission). The
-- link lets readers replace the original's trades with the amendment's even when the amendment corrects a trade date
-- (pipeline/signals/insiders.latest_versions). Null for original filings and for India's disclosures.
alter table insider_events add column amends date;

-- The web's read-only view carries the link too, so the M7 company page can show a Form 4 and its 4/A as one
-- purchase (a new column goes last: create or replace keeps the view's grants).
create or replace view insider_events_display_v with (security_invoker = true) as
  select e.id, e.company_id, e.event_date, e.filed_at, e.person, e.role, e.kind, e.shares, e.value, e.currency,
         e.planned, e.source_url, e.amends
  from insider_events e;

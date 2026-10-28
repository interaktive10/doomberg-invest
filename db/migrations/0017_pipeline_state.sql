-- 0017: durable pipeline state (docs/SPEC_ISSUES.md 55). The India jobs' state files (listing cursors, download queues,
-- each company's parsed results history) and the Signal Lab's Twelve Data download lived in the Actions cache, which
-- evicts an entry after 7 days unused (India's was lost in the pause), and in the lab-data-v1 release, which became
-- public with the repository (BRIEF §1.2.6: free data is for personal use, never redistributed). One gzipped body per
-- name, written by `python -m pipeline.db.state put` and read back by `get`. Service role only, like every table (0002).
create table pipeline_state (name text primary key check (name ~ '^[a-z0-9_]+$'), body bytea not null,
  bytes int not null check (bytes >= 0), saved_at timestamptz not null default now());
alter table pipeline_state enable row level security;

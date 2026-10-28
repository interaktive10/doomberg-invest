-- 0018: the Watch bucket (docs/SPEC_ISSUES.md 56): one family at full strength, no red flag, revenue up on a year and a
-- Gap of 60 or more; only each market's top few a week (config/signals.yaml scores.buckets.watch).
alter table scores drop constraint scores_bucket_check;
alter table scores add constraint scores_bucket_check
  check (bucket in ('candidate', 'priced_in', 'early', 'watch', 'excluded', 'none'));

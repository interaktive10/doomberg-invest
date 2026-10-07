-- 0014: two source_health rows that can never succeed (docs/SPEC_ISSUES.md 40). 'stooq' came back after 0012
-- dropped it: quarterly.yml re-seeds source_health from pipeline.db.seed.SOURCES, which still listed it. 'fred' has
-- no reader: no formula or job asks FRED. Both read "never succeeded" in the digest and in Settings.
delete from source_health where source in ('stooq', 'fred');

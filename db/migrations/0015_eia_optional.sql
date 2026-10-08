-- 0015: EIA is optional (docs/SPEC_ISSUES.md 44): Manzoor runs without an EIA key, so the Capex Desk index uses its
-- other inputs and the 'eia' row would read "never succeeded" forever. A run with a key records the row again.
delete from source_health where source = 'eia' and last_success is null;

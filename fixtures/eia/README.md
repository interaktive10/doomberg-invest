# fixtures/eia

EIA API v2 `electricity/operating-generator-capacity` answers in the shape EIA documents (`response.total`, `response.data[]` with `period`, `status`, `technology`, `nameplate-capacity-mw`). They are **not recordings**: api.eia.gov can't be reached from the build container (docs/SPEC_ISSUES.md). Two pages of one 5-row answer, for the paging and parsing tests in `tests/capex/test_eia.py`. Replace them with a real response once the key (EIA_API_KEY) works from a runner.

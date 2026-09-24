# Spec issues (building as written; flagged for Manzoor)

1. **Appendix H says "US (60)" but lists 61 tickers.** The 61 are carried over unchanged into `config/capex_seed.yaml`, and `tests/test_config_matches_brief.py` pins all 61. Decide whether one should go.
2. **Short interest has no free source in §2.7.** The old Doomberg `most_shorted_stocks` lane (audit §5 and §7.7) can't be tested in the Lab without one. FINRA's bi-monthly equity short-interest files are free. Adding them would need §2.7 and allowlist changes.
3. **§1.3 "trusts" is ambiguous.** A literal reading would drop REITs (SIC 6798), which would drop EQIX, DLR and IRM from the capex seed. Built with royalty/grantor trusts only (see DECISIONS.log).
4. **The M0 PR necessarily touches protected paths** (`config/guards.yaml`, `config/signals.yaml`, `config/weights.yaml`, `config/context.yaml`, `config/redflags.yaml`, `scripts/guard.py`, `tests/guard/**`, `.claude/agents/reviewer.md`), because M0 creates them. The `protected` CI job fails until the `human-approved` label is added to the M0 PR. That's by design (Appendix D).

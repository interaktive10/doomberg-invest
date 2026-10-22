# Doomberg Invest

Private, single-user research app for long-term investing (US; India is paused). It finds companies whose evidence of
fundamental change the market hasn't priced, and turns each into a thesis card. $0 running cost. **Research only, not
financial advice. No broker connections, no order placement, no intraday data.**

- Spec: [`docs/BRIEF.md`](docs/BRIEF.md) · Repo guide for Claude Code: [`CLAUDE.md`](CLAUDE.md)
- What was learned from the old Doomberg: [`docs/DOOMBERG_AUDIT.md`](docs/DOOMBERG_AUDIT.md)

```bash
make setup      # Python 3.12 + locked deps (uv)
make test       # offline test suite
make guard      # BRIEF Appendix E guard
make verify-m8  # every milestone's checks (CI runs this) -> docs/VERIFY_REPORT.md (not committed)
make universe   # (network) universe snapshots
```

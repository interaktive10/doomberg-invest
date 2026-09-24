# Doomberg Invest

Private, single-user research app for long-term investing (US + India). Two desks: **Opportunities** (evidence of
fundamental change the market hasn't priced) and **Capex** (AI and infrastructure capex across the supply chain,
including Indian suppliers). $0 running cost. **Research only, not financial advice. No broker connections, no order
placement, no intraday data.**

- Spec: [`docs/BRIEF.md`](docs/BRIEF.md) · Repo guide for Claude Code: [`CLAUDE.md`](CLAUDE.md)
- What was learned from the old Doomberg: [`docs/DOOMBERG_AUDIT.md`](docs/DOOMBERG_AUDIT.md)
- Latest verify run: [`docs/VERIFY_REPORT.md`](docs/VERIFY_REPORT.md)

```bash
make setup      # Python 3.12 + locked deps (uv)
make test       # offline test suite
make guard      # BRIEF Appendix E guard
make verify-m0  # milestone checks -> docs/VERIFY_REPORT.md
make universe   # (network) universe snapshots + capex seed resolution
```

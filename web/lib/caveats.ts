// BRIEF §7: the first four honest limits, verbatim (markdown as in the brief), printed at the top of the Signal Lab
// screen; pipeline/lab/report.py prints the same four in every Lab report. tests/caveats.test.ts compares them
// with docs/BRIEF.md.
export const CAVEATS = [
  "1. No signal set reliably beats the market. The Lab exists to find out, and most signals will fail out of sample. That's useful information, not a bug.",
  "2. **Survivorship bias:** the free US price file may miss delisted companies, so Lab results are an optimistic upper bound.",
  "3. Lab returns exclude dividends (v1), taxes and costs.",
  "4. The reverse DCF is a rough lens (one growth rate, generic discount rates). It ranks expectations; it doesn't value companies.",
] as const;

// Mirror of app/globals.css @theme; SVG attributes (recharts, cytoscape) can't read CSS vars. Change both together:
// tests/palette.test.ts pins these to the theme.
export const INK = {
  grid: "#1d2632", // --color-line
  axis: "#2c3947", // --color-line-strong
  tick: "#8494a5", // --color-subtle
  fg: "#e7edf3", // --color-fg
  muted: "#a3b1bf", // --color-muted
  tip: "#121821", // --color-raised
  edge: "#5f7084", // --color-edge
  panel: "#0c1016", // --color-panel
} as const;

/** Chart series colours, in order: accent, violet, pink, fg. The second and later series are also dashed. */
export const SERIES = ["#4cc3ff", "#b79cff", "#ff9ecf", "#e7edf3"] as const;

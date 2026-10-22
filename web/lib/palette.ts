// The look (overhaul PR 6): Curator's calm light theme and its charcoal dark one. app/globals.css defines every
// colour token below as a CSS variable (--canvas, --panel, ...) for light, and again for dark under the Auto media
// query and under data-theme="dark"; Tailwind reads them as bg-canvas, text-fg and so on. This file mirrors the hex
// values (tests/palette.test.ts pins both themes to the stylesheet and checks every text colour reaches 4.5:1 on every
// surface) and hands SVG and inline styles `var(--token)` references, so a chart follows the theme with no re-render.

export const LIGHT = {
  // surfaces
  canvas: "#f5f6f8", // the page
  panel: "#ffffff", // sheets (Section), menus, the active nav pill's ground
  raised: "#f7f8fa", // tiles inside a sheet
  hover: "#f1f3f6", // chips, secondary pills, row hover
  field: "#ffffff", // inputs
  track: "#e6e8ee", // ring and bar tracks, the segmented nav's track
  thumb: "#ffffff", // the segmented nav's active pill
  line: "#ebecef", // hairlines between rows
  "line-strong": "#d9dbe0", // field borders, dashed empties
  edge: "#8a8a90", // control borders that must stand out (>= 3:1)
  // text
  fg: "#1c1c1e",
  muted: "#55555b", // secondary text
  subtle: "#636369", // meta text, eyebrows, placeholders
  // actions
  accent: "#3656d6", // links, focus, the Evidence ring, count pills
  "accent-hover": "#2a47b8",
  "on-accent": "#ffffff",
  ink: "#1c1c1e", // primary pills
  "on-ink": "#ffffff",
  // meaning
  up: "#2b6d44", // good
  down: "#a33a3a", // bad
  warn: "#8a5a2a", // needs a look
  violet: "#6e5bbf", // chart series 2 only
  gap: "#3f8a5b", // the Gap ring and bars (a fill, never text: use up for green text)
  // evidence families (dots and bars; the text beside them carries the meaning)
  "fam-business": "#6f9478",
  "fam-insiders": "#7089ab",
  "fam-ownership": "#c29b5a",
  "fam-text": "#b58468",
  // ticker tiles
  "tint-sky": "#e7eefb",
  "tint-sage": "#e8f1ea",
  "tint-sand": "#f6efe2",
  "tint-clay": "#f5ebe5",
} as const;

export type Token = keyof typeof LIGHT;

export const DARK: Record<Token, string> = {
  canvas: "#0b0c0e",
  panel: "#1a1b1f",
  raised: "#222328",
  hover: "#2a2b30",
  field: "#141518",
  track: "#2e2f35",
  thumb: "#34353b",
  line: "#28292e",
  "line-strong": "#3a3b41",
  edge: "#6e6e76",
  fg: "#f2f2f4",
  muted: "#b4b4ba",
  subtle: "#9b9ba2",
  accent: "#9bb0cb",
  "accent-hover": "#b9c8dd",
  "on-accent": "#0b0c0e",
  ink: "#f2f2f4",
  "on-ink": "#0b0c0e",
  up: "#7aab8a",
  down: "#d98080",
  warn: "#d4a574",
  violet: "#b4a8e6",
  gap: "#7aab8a",
  "fam-business": "#93b39a",
  "fam-insiders": "#a0b4ce",
  "fam-ownership": "#d6b77e",
  "fam-text": "#c99d82",
  "tint-sky": "#2a3550",
  "tint-sage": "#24382c",
  "tint-sand": "#3d3424",
  "tint-clay": "#3d2e27",
};

/** The token as a CSS colour that follows the theme (for SVG attributes and inline styles). */
export function cssVar(token: Token): string {
  return `var(--${token})`;
}

/** Chart ink (components/charts.tsx). */
export const INK = {
  grid: "var(--line)",
  axis: "var(--line-strong)",
  tick: "var(--subtle)",
  fg: "var(--fg)",
  muted: "var(--muted)",
  tip: "var(--panel)",
  edge: "var(--edge)",
  panel: "var(--panel)",
  track: "var(--track)",
} as const;

/** Chart series colours, in order: accent, violet, ownership amber, fg. The second and later series are also dashed. */
export const SERIES = ["var(--accent)", "var(--violet)", "var(--fam-ownership)", "var(--fg)"] as const;

/** What a dot, a bar or a sparkline is coloured by: an evidence family, a score, or a meaning. */
export type Tone = "business" | "insiders" | "ownership" | "text" | "evidence" | "gap" | "up" | "down" | "warn" | "muted";

export const TONE_VAR: Record<Tone, string> = {
  business: "var(--fam-business)",
  insiders: "var(--fam-insiders)",
  ownership: "var(--fam-ownership)",
  text: "var(--fam-text)",
  evidence: "var(--accent)",
  gap: "var(--gap)",
  up: "var(--up)",
  down: "var(--down)",
  warn: "var(--warn)",
  muted: "var(--subtle)",
};

/** Plain words for a tone that is an evidence family (legends, tooltips). */
export const TONE_WORD: Partial<Record<Tone, string>> = {
  business: "business",
  insiders: "insiders",
  ownership: "ownership",
  text: "text facts",
};

/** The colour of a pipeline family (scores.families, lib/why.ts FAMILIES): fundamentals are the business, behavior is
 * insiders, text is text facts; structural (special situations) reads as ownership; anything else is grey. */
export function familyTone(family: string): Tone {
  switch (family) {
    case "fundamentals":
      return "business";
    case "behavior":
      return "insiders";
    case "text":
      return "text";
    case "structural":
      return "ownership";
    default:
      return "muted";
  }
}

/** The colour of one signal (BRIEF §1.4): S1-S6 the business, S7 insiders, S8 (13F discovery) and S10 ownership, S9
 * text facts, the rest grey. */
export function signalTone(code: string): Tone {
  const n = /^S(\d+)$/.exec(code.trim().toUpperCase())?.[1];
  const i = n === undefined ? Number.NaN : Number(n);
  if (i >= 1 && i <= 6) return "business";
  if (i === 7) return "insiders";
  if (i === 8 || i === 10) return "ownership";
  if (i === 9) return "text";
  return "muted";
}

// The look (overhaul PR 6): Curator's calm light theme and its charcoal dark one. app/globals.css defines every
// colour token below as a CSS variable (--canvas, --panel, ...) for light, and again for dark under the Auto media
// query and under data-theme="dark"; Tailwind reads them as bg-canvas, text-fg and so on. This file mirrors the hex
// values (tests/palette.test.ts pins both themes to the stylesheet and checks every text colour reaches 4.5:1 on every
// surface) and hands SVG and inline styles `var(--token)` references, so a chart follows the theme with no re-render.

export const LIGHT = {
  // surfaces
  canvas: "#f6f5f0", // the page
  panel: "#ffffff", // sheets (Section), menus, the active nav pill's ground
  raised: "#f8f7f3", // tiles inside a sheet
  hover: "#f0eee7", // chips, secondary pills, row hover
  field: "#ffffff", // inputs
  track: "#e8e5dc", // ring and bar tracks, the segmented nav's track
  thumb: "#ffffff", // the segmented nav's active pill
  line: "#ebe9e2", // hairlines between rows
  "line-strong": "#d8d5cb", // field borders, dashed empties
  edge: "#85837c", // control borders that must stand out (>= 3:1)
  // text
  fg: "#18181b",
  muted: "#4f4f57", // secondary text
  subtle: "#5e5e66", // meta text, eyebrows, placeholders
  // actions
  accent: "#4f46e5", // links, focus, the Evidence ring, count pills
  "accent-hover": "#4338ca",
  "on-accent": "#ffffff",
  ink: "#18181b", // primary pills
  "on-ink": "#ffffff",
  // meaning
  up: "#166534", // good
  down: "#a3123a", // bad
  warn: "#7f4a06", // needs a look
  violet: "#7c3aed", // chart series 2 only
  gap: "#16a34a", // the Gap ring and bars (a fill, never text: use up for green text)
  // evidence families (dots and bars; the text beside them carries the meaning)
  "fam-business": "#3fa66a",
  "fam-insiders": "#4f7fd9",
  "fam-ownership": "#e0a12e",
  "fam-text": "#e0714a",
  // ticker tiles
  "tint-sky": "#e8ebff",
  "tint-sage": "#e1f4e7",
  "tint-sand": "#fcf0d6",
  "tint-clay": "#fde8df",
  // Winners
  pink: "#db2777",
  "tint-rose": "#fde6f0",
} as const;

export type Token = keyof typeof LIGHT;

export const DARK: Record<Token, string> = {
  canvas: "#0d0d10",
  panel: "#1a1a1f",
  raised: "#222228",
  hover: "#2a2a31",
  field: "#141418",
  track: "#2f2f37",
  thumb: "#4a4a54",
  line: "#29292f",
  "line-strong": "#3b3b43",
  edge: "#70707a",
  fg: "#f4f4f5",
  muted: "#b6b6be",
  subtle: "#9d9da6",
  accent: "#a5b4fc",
  "accent-hover": "#c7d2fe",
  "on-accent": "#0d0d10",
  ink: "#f4f4f5",
  "on-ink": "#0d0d10",
  up: "#7ddc9f",
  down: "#fb8fa3",
  warn: "#f5c04a",
  violet: "#c4b5fd",
  gap: "#4ade80",
  "fam-business": "#6cc58f",
  "fam-insiders": "#8fb0f0",
  "fam-ownership": "#f2c463",
  "fam-text": "#f29a78",
  "tint-sky": "#262b4d",
  "tint-sage": "#1c3828",
  "tint-sand": "#3d311d",
  "tint-clay": "#41271e",
  pink: "#f472b6",
  "tint-rose": "#43203a",
};

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

/** A sparkline card's own colour for its first series (the Company mock: revenue in the accent, operating income in the
 * business green, cash from operations in the insiders blue). */
export const CHART_TONE = {
  accent: "var(--accent)",
  business: "var(--fam-business)",
  insiders: "var(--fam-insiders)",
  ownership: "var(--fam-ownership)",
  text: "var(--fam-text)",
} as const;

export type ChartTone = keyof typeof CHART_TONE;

/** What a dot or a bar is coloured by: an evidence family, a score, or a meaning (components/chip.tsx and meter.tsx
 * map each to its theme class). */
export type Tone = "business" | "insiders" | "ownership" | "text" | "evidence" | "gap" | "up" | "down" | "warn" | "muted";

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

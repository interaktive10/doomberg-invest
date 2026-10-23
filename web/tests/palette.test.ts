import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CHART_TONE, DARK, familyTone, INK, LIGHT, SERIES, signalTone, type Token } from "@/lib/palette";

// The look (overhaul PR 6, app/globals.css): every colour is a CSS variable defined for light on :root and for dark
// twice (the Auto media query and data-theme="dark"); Tailwind reads them through @theme inline, which resets Tailwind's
// own colours (`--color-*: initial`). So a stock palette class (a gray, blue or white) left in a screen compiles to no
// CSS at all instead of failing the build, and a hex colour in a screen can't follow the theme: these scans fail
// instead. They also ban custom font-size tokens: tailwind-merge (cn()) reads an unknown text-<name> as a text colour,
// so merging one with a colour class silently drops the size. lib/palette.ts mirrors the values; the contrast checks
// below hold both themes to 4.5:1 for every text colour on every surface (axe runs at 390 px in one theme only).

const WEB = fileURLToPath(new URL("..", import.meta.url));
const OLD =
  /\b(?:bg|text|border(?:-[tlrbxy])?|ring|outline|decoration|divide|fill|stroke|accent|placeholder:text)-(?:white|black|gray|zinc|slate|neutral|blue|red|green|amber|emerald|indigo)(?:-\d{2,3})?(?:\/\d+)?\b/g;
const SIZE = /\btext-(?:ui|2xs)\b/g;
const HEX = /#[0-9a-f]{6}\b/gi;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(f) ? [p] : [];
  });
}

const CSS_FILE = join(WEB, "app", "globals.css");
const CSS = readFileSync(CSS_FILE, "utf8");
const SCREENS = [...files(join(WEB, "app")), ...files(join(WEB, "components"))];
const SCANNED = [...SCREENS, CSS_FILE];

function hits(re: RegExp, in_: readonly string[] = SCANNED): string[] {
  return in_.flatMap((f) => [...readFileSync(f, "utf8").matchAll(re)].map((m) => `${relative(WEB, f)}: ${m[0]}`));
}

/** The body of the first block `selector {` opens in the stylesheet (blocks here hold no nested braces). */
function block(selector: string): string {
  const at = CSS.indexOf(`${selector} {`);
  if (at < 0) return "";
  const open = CSS.indexOf("{", at);
  return CSS.slice(open + 1, CSS.indexOf("}", open));
}

/** A block's custom properties: name (without the dashes) -> value. */
function vars(body: string): Record<string, string> {
  return Object.fromEntries([...body.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)].map((m) => [m[1]!, m[2]!.trim()]));
}

const LIGHT_VARS = vars(block(":root"));
const AUTO_DARK_VARS = vars(block(':root:not([data-theme="light"])'));
const DARK_VARS = vars(block(':root[data-theme="dark"]'));
const TOKENS = Object.keys(LIGHT) as Token[];

// WCAG 2.x contrast.
function rgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];
}
function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
/** `share` of colour a over b (a badge's tint: bg-down/10 over the panel). */
function mix(a: string, b: string, share: number): string {
  const [p, q] = [rgb(a), rgb(b)];
  return `#${p.map((v, i) => Math.round(v * share + q[i]! * (1 - share)).toString(16).padStart(2, "0")).join("")}`;
}

const SURFACES: Token[] = ["canvas", "panel", "raised", "hover", "field"];
const TEXTS: Token[] = ["fg", "muted", "subtle", "accent", "accent-hover", "up", "down", "warn"];
const TINTED: Token[] = ["accent", "up", "down", "warn"];

describe("palette guard (the Curator look, light and dark)", () => {
  it("scans the screens, the components and the stylesheet", () => {
    expect(SCANNED.length).toBeGreaterThan(20);
    expect(SCANNED.some((f) => f.endsWith(join("components", "page.tsx")))).toBe(true);
  });

  it("finds a stock palette class, a custom text token or a hex colour where one is planted", () => {
    const planted = 'className="bg-white text-gray-700 border-t-red-200 hover:bg-blue-50/80 placeholder:text-gray-500 text-ui" fill="#1C1C1E"';
    expect(planted.match(OLD)).toEqual(["bg-white", "text-gray-700", "border-t-red-200", "bg-blue-50/80", "placeholder:text-gray-500"]);
    expect(planted.match(SIZE)).toEqual(["text-ui"]);
    expect(planted.match(HEX)).toEqual(["#1C1C1E"]);
    expect("bg-canvas text-fg border-line ring-line-strong text-accent bg-tint-sage bg-fam-business bg-down/10 text-[13px]".match(OLD)).toBeNull();
    expect('href="#main" href="/settings#sources"'.match(HEX)).toBeNull();
  });

  it("uses only the theme's colour names", () => {
    expect(hits(OLD)).toEqual([]);
  });

  it("sets small font sizes with arbitrary values, not custom text tokens", () => {
    expect(hits(SIZE)).toEqual([]);
  });

  it("writes no hex colour in a screen or a component (a token follows the theme; a hex can't)", () => {
    expect(hits(HEX, SCREENS)).toEqual([]);
  });

  it("defines every colour token for light, and the same dark values under Auto and under Dark", () => {
    expect(TOKENS.length).toBeGreaterThan(20);
    expect(Object.keys(DARK).sort()).toEqual([...TOKENS].sort());
    expect(Object.fromEntries(TOKENS.map((t) => [t, LIGHT_VARS[t]]))).toEqual(LIGHT);
    expect(Object.fromEntries(TOKENS.map((t) => [t, DARK_VARS[t]]))).toEqual(DARK);
    // the two dark blocks are the same, and dark sets every variable light does (shadows and glass too)
    expect(AUTO_DARK_VARS).toEqual(DARK_VARS);
    expect(Object.keys(DARK_VARS).sort()).toEqual(Object.keys(LIGHT_VARS).sort());
    // Auto: the media query yields to a chosen Light; Dark: the attribute the root layout writes
    expect(CSS).toMatch(/@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme="light"\]\) \{/);
    expect(block(":root")).toMatch(/color-scheme: light;/);
    expect(block(':root[data-theme="dark"]')).toMatch(/color-scheme: dark;/);
  });

  it("maps every token, and only those, to a Tailwind colour that reads its variable", () => {
    const theme = block("@theme inline");
    expect(theme).toMatch(/--color-\*: initial;/);
    expect(vars(theme)).toEqual(Object.fromEntries(TOKENS.map((t) => [`color-${t}`, `var(--${t})`])));
  });

  it("gives every text colour 4.5:1 on every surface, in both themes", () => {
    const low: string[] = [];
    const need = (theme: string, what: string, fg: string, bg: string) => {
      const r = contrast(fg, bg);
      if (r < 4.5) low.push(`${theme}: ${what} ${r.toFixed(2)}`);
    };
    for (const [name, t] of [["light", LIGHT], ["dark", DARK]] as const) {
      for (const text of TEXTS) for (const s of SURFACES) need(name, `${text} on ${s}`, t[text], t[s]);
      // segmented pills (the header's nav, components/segmented.tsx): labels on the track, the current one in fg on the
      // thumb (its count is a CountPill, on-accent on accent, checked below)
      for (const text of ["fg", "muted", "accent"] as const) need(name, `${text} on track`, t[text], t.track);
      need(name, "fg on thumb", t.fg, t.thumb);
      // pills and count badges
      need(name, "on-accent on accent", t["on-accent"], t.accent);
      need(name, "on-ink on ink", t["on-ink"], t.ink);
      // a soft chip: a colour's own text on its tint (Badge uses 10%; 12% here leaves a margin), also on a row that
      // hovers to the hover grey (the Theses rows' kill-criteria chip; PR 6 review a11y-A11Y-7)
      for (const c of TINTED) for (const s of ["canvas", "panel", "raised", "hover"] as const) need(name, `${c} on its tint over ${s}`, t[c], mix(t[c], t[s], 0.12));
      // ticker tiles
      for (const tint of ["tint-sky", "tint-sage", "tint-sand", "tint-clay"] as const) need(name, `fg on ${tint}`, t.fg, t[tint]);
    }
    expect(low).toEqual([]);
  });

  it("draws control edges at 3:1 or more on every ground a field sits on, in both themes (PR 6 review a11y-A11Y-1)", () => {
    const low: string[] = [];
    for (const [name, t] of [["light", LIGHT], ["dark", DARK]] as const) {
      for (const s of ["canvas", "panel", "raised", "field"] as const) {
        const r = contrast(t.edge, t[s]);
        if (r < 3) low.push(`${name}: edge on ${s} ${r.toFixed(2)}`);
      }
    }
    expect(low).toEqual([]);
    // fields, choice pills, the outline button and the header's search box draw their edge in it
    const ui = (f: string) => readFileSync(join(WEB, f), "utf8");
    expect(ui("components/ui/input.tsx")).not.toMatch(/border-line-strong/);
    expect(ui("components/ui/input.tsx").match(/\bborder-edge\b/g)?.length).toBe(2); // field and choiceChip
    expect(ui("components/ui/button.tsx")).toMatch(/outline: "[^"]*\bring-edge\b/);
    expect(ui("components/nav-links.tsx")).toMatch(/lift [^"]*\boutline-edge\b/);
  });

  it("lifts the current segment off the track in dark, where the thumb's shadow barely shows (PR 6 review a11y-A11Y-2)", () => {
    expect(contrast(DARK.thumb, DARK.track)).toBeGreaterThanOrEqual(1.5);
  });

  it("reads only variables the stylesheet defines, by their own names (Tailwind's --color-* need not exist at run time)", () => {
    const own = new Set([...Object.keys(LIGHT_VARS), "font-inter"]);
    const refs = hits(/var\(--([a-z0-9-]+)/g, SCREENS).map((h) => h.replace(/var\(--/, ""));
    expect(refs.filter((r) => !own.has(r.split(": ")[1]!))).toEqual([]);
    expect(hits(/var\(--color-/g, SCREENS)).toEqual([]);
  });

  it("hands the charts' SVG theme variables that exist", () => {
    const refs = [...Object.values(INK), ...SERIES, ...Object.values(CHART_TONE)];
    const names = refs.map((v) => /^var\(--([a-z0-9-]+)\)$/.exec(v)?.[1]);
    expect(names.filter((n) => n === undefined || !(n in LIGHT))).toEqual([]);
  });

  it("colours the pipeline's families and signals with the four family colours", () => {
    expect(["fundamentals", "behavior", "text", "structural", "cycle"].map(familyTone)).toEqual(["business", "insiders", "text", "ownership", "muted"]);
    expect(["S1", "S6", "S7", "S8", "S9", "S10", "S12", "s4", "R2", ""].map(signalTone)).toEqual([
      "business",
      "business",
      "insiders",
      "ownership",
      "text",
      "ownership",
      "muted",
      "business",
      "muted",
      "muted",
    ]);
  });
});

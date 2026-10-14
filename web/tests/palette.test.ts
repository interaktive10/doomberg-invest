import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { INK, SERIES } from "@/lib/palette";

// The dark terminal look (app/globals.css @theme) resets Tailwind's colours (`--color-*: initial`), so a stock palette
// class (a gray, blue or white) left in a screen compiles to no CSS at all instead of failing the build. This scan
// fails instead. It also bans custom font-size tokens: tailwind-merge (cn()) reads an unknown text-<name> as a text
// colour, so merging one with a colour class silently drops the size.

const WEB = fileURLToPath(new URL("..", import.meta.url));
const OLD =
  /\b(?:bg|text|border(?:-[tlrbxy])?|ring|outline|decoration|divide|fill|stroke|accent|placeholder:text)-(?:white|black|gray|zinc|slate|neutral|blue|red|green|amber|emerald|indigo)(?:-\d{2,3})?(?:\/\d+)?\b/g;
const SIZE = /\btext-(?:ui|2xs)\b/g;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(f) ? [p] : [];
  });
}

const SCANNED = [...files(join(WEB, "app")), ...files(join(WEB, "components")), join(WEB, "app", "globals.css")];

function hits(re: RegExp): string[] {
  return SCANNED.flatMap((f) => [...readFileSync(f, "utf8").matchAll(re)].map((m) => `${relative(WEB, f)}: ${m[0]}`));
}

/** A `--color-<name>: #hex;` line of the theme. */
function token(name: string): string | undefined {
  const css = readFileSync(join(WEB, "app", "globals.css"), "utf8");
  return new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})\\s*;`, "i").exec(css)?.[1]?.toLowerCase();
}

describe("palette guard (the dark terminal look)", () => {
  it("scans the screens, the components and the stylesheet", () => {
    expect(SCANNED.length).toBeGreaterThan(20);
    expect(SCANNED.some((f) => f.endsWith(join("components", "page.tsx")))).toBe(true);
  });

  it("finds a stock palette class or a custom text token where one is planted", () => {
    const planted = 'className="bg-white text-gray-700 border-t-red-200 hover:bg-blue-50/80 placeholder:text-gray-500 text-ui"';
    expect(planted.match(OLD)).toEqual(["bg-white", "text-gray-700", "border-t-red-200", "bg-blue-50/80", "placeholder:text-gray-500"]);
    expect(planted.match(SIZE)).toEqual(["text-ui"]);
    expect("bg-canvas text-fg border-line ring-line-strong text-accent border-t-up bg-down/15 text-[13px]".match(OLD)).toBeNull();
  });

  it("uses only the theme's colour names", () => {
    expect(hits(OLD)).toEqual([]);
  });

  it("sets small font sizes with arbitrary values, not custom text tokens", () => {
    expect(hits(SIZE)).toEqual([]);
  });

  it("keeps lib/palette.ts (SVG colours) equal to the theme", () => {
    expect([INK.grid, INK.axis, INK.tick, INK.fg, INK.muted, INK.tip, INK.edge, INK.panel]).toEqual(
      ["line", "line-strong", "subtle", "fg", "muted", "raised", "edge", "panel"].map(token),
    );
    expect([SERIES[0], SERIES[1], SERIES[3]]).toEqual(["accent", "violet", "fg"].map(token));
  });
});

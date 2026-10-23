import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { nextTheme, parseTheme, resolvedTheme, THEME_COOKIE, THEME_MAX_AGE, themeCookie, themeLabel } from "@/lib/theme";

const WEB = fileURLToPath(new URL("..", import.meta.url));

describe("theme switch (lib/theme.ts)", () => {
  it("reads the cookie as a mode: Light, Dark, else Auto", () => {
    expect(parseTheme("light")).toBe("light");
    expect(parseTheme("dark")).toBe("dark");
    for (const v of [undefined, null, "", "auto", "Dark", "dark;", "<script>"]) expect(parseTheme(v)).toBe("auto");
  });

  it("cycles Auto, Light, Dark and back to Auto", () => {
    expect(nextTheme("auto")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("auto");
  });

  it("names the mode the button is in", () => {
    expect(themeLabel("auto")).toBe("Theme: Auto (follows your device)");
    expect(themeLabel("light")).toBe("Theme: Light");
    expect(themeLabel("dark")).toBe("Theme: Dark");
  });

  it("keeps Light or Dark for 400 days on every path, and Auto deletes the cookie", () => {
    expect(THEME_MAX_AGE).toBe(34_560_000);
    expect(themeCookie("dark")).toBe(`${THEME_COOKIE}=dark; Path=/; Max-Age=34560000; SameSite=Lax`);
    expect(themeCookie("light")).toBe("theme=light; Path=/; Max-Age=34560000; SameSite=Lax");
    expect(themeCookie("auto")).toBe("theme=; Path=/; Max-Age=0; SameSite=Lax");
  });

  it("resolves Auto to the device's theme and keeps a chosen one", () => {
    expect(resolvedTheme("auto", true)).toBe("dark");
    expect(resolvedTheme("auto", false)).toBe("light");
    expect(resolvedTheme("light", true)).toBe("light");
    expect(resolvedTheme("dark", false)).toBe("dark");
  });

  it("is written on <html> by the root layout from the server's reading of the cookie (no flash)", () => {
    const layout = readFileSync(`${WEB}/app/layout.tsx`, "utf8");
    expect(layout).toContain("data-theme={mode === \"auto\" ? undefined : mode}");
    expect(layout).toContain("await themeMode()");
    const server = readFileSync(`${WEB}/lib/theme-server.ts`, "utf8");
    expect(server).toContain('import "server-only"');
    expect(server).toContain("THEME_COOKIE");
  });
});

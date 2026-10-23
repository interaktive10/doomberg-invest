// The theme switch (overhaul PR 6): Auto (the default) follows the device's light or dark setting through the
// stylesheet's prefers-color-scheme query; Light and Dark are kept in a cookie that the root layout reads on the
// server and writes as data-theme on <html>, so the first paint is already right (no flash). Pure, so
// tests/theme.test.ts covers it; lib/theme-server.ts reads the cookie, components/theme-switch.tsx writes it.

export type ThemeMode = "auto" | "light" | "dark";

export const THEME_COOKIE = "theme";
/** The order the button cycles through. */
export const THEME_MODES: readonly ThemeMode[] = ["auto", "light", "dark"];
/** 400 days: the longest a browser keeps a cookie. */
export const THEME_MAX_AGE = 400 * 24 * 60 * 60;

export const THEME_NAME: Record<ThemeMode, string> = { auto: "Auto", light: "Light", dark: "Dark" };

/** The cookie's value as a mode: anything but "light" or "dark" (no cookie, an old or forged value) is Auto. */
export function parseTheme(value: string | null | undefined): ThemeMode {
  return value === "light" || value === "dark" ? value : "auto";
}

/** The mode after `mode` on the button: Auto, Light, Dark, Auto. */
export function nextTheme(mode: ThemeMode): ThemeMode {
  return THEME_MODES[(THEME_MODES.indexOf(mode) + 1) % THEME_MODES.length] ?? "auto";
}

/** The button's accessible name: the mode it is in now. */
export function themeLabel(mode: ThemeMode): string {
  return mode === "auto" ? "Theme: Auto (follows your device)" : `Theme: ${THEME_NAME[mode]}`;
}

/** The document.cookie assignment that stores `mode`; Auto deletes the cookie. A display preference, readable by the
 * page on purpose, with no session data in it. */
export function themeCookie(mode: ThemeMode): string {
  return mode === "auto"
    ? `${THEME_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`
    : `${THEME_COOKIE}=${mode}; Path=/; Max-Age=${THEME_MAX_AGE}; SameSite=Lax`;
}

/** The theme a page shows: the chosen one, or the device's under Auto. */
export function resolvedTheme(mode: ThemeMode, deviceDark: boolean): "light" | "dark" {
  return mode === "auto" ? (deviceDark ? "dark" : "light") : mode;
}

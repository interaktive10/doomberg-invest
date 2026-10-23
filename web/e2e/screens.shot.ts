import { test } from "@playwright/test";
import { PAGES } from "./seed";

// Screenshots of every screen at a desktop and a phone width, and the phone again in the dark theme (the approved
// phone artboard is dark; overhaul PR 6 review design-F8), for reviewing the UI (not a behaviour test: `pnpm screens`,
// run by .github/workflows/ui-screens.yml, which publishes them to the ui-screens branch). SHOTS_SET=empty takes the
// top-level screens on a migrated but empty database first (what a new deployment shows before its first weekly run),
// plus a page that doesn't exist.
const WIDTHS = [
  { name: "desktop", width: 1280, height: 900, colorScheme: "light" },
  { name: "phone", width: 390, height: 844, colorScheme: "light" },
  { name: "phone-dark", width: 390, height: 844, colorScheme: "dark" },
] as const;

const EMPTY = process.env.SHOTS_SET === "empty";
const SET: readonly string[] = EMPTY
  ? ["/", "/candidates", "/theses", "/journal", "/lab", "/settings", "/company/00000000-0000-4000-8000-000000000000"]
  : PAGES;
const PREFIX = EMPTY ? "empty-" : "";

function slug(path: string): string {
  const s = path === "/" ? "home" : path.slice(1);
  return s.replace(/[^a-z0-9]+/gi, "-").replace(/-+$/, "").slice(0, 48);
}

for (const w of WIDTHS) {
  test.describe(w.name, () => {
    test.use({ viewport: { width: w.width, height: w.height }, colorScheme: w.colorScheme });
    for (const [i, path] of SET.entries()) {
      test(`${w.name} ${path}`, async ({ page }) => {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        const name = `${PREFIX}${String(i + 1).padStart(2, "0")}-${slug(path)}-${w.name}.png`;
        await page.screenshot({ path: `screenshots/${name}`, fullPage: true });
      });
    }
  });

  test.describe(`${w.name} signed out`, () => {
    test.use({ viewport: { width: w.width, height: w.height }, colorScheme: w.colorScheme, storageState: { cookies: [], origins: [] } });
    test(`${w.name} /login`, async ({ page }) => {
      await page.goto("/login");
      await page.waitForLoadState("networkidle");
      await page.screenshot({ path: `screenshots/${PREFIX}00-login-${w.name}.png`, fullPage: true });
    });
  });
}

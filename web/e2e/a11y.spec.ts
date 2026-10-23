import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { PAGES } from "./seed";

// BRIEF §8 M7-03: axe reports no serious (or critical) issue, and every screen fits a 390 px phone without sideways
// page scrolling (wide tables scroll inside their own box). In both themes (overhaul PR 6; review design-F8): the
// device's light scheme, and its dark one, which Auto follows.
test.use({ viewport: { width: 390, height: 844 } });

async function check(page: Page): Promise<void> {
  const result = await new AxeBuilder({ page }).analyze();
  const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 5).join(" | ")}`)).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

for (const scheme of ["light", "dark"] as const) {
  test.describe(scheme, () => {
    test.use({ colorScheme: scheme });

    for (const path of PAGES) {
      test(`axe and 390 px, ${scheme}: ${path}`, async ({ page }) => {
        await page.goto(path);
        await expect(page.locator("main h1").first()).toBeVisible();
        await page.waitForLoadState("networkidle");
        await check(page);
      });
    }

    test.describe("signed out", () => {
      test.use({ storageState: { cookies: [], origins: [] } });
      test(`axe and 390 px, ${scheme}: /login`, async ({ page }) => {
        await page.goto("/login");
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await check(page);
      });
    });
  });
}

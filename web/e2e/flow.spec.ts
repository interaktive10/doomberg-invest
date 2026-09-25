import { expect, test, type Page } from "@playwright/test";

// BRIEF §8 M7-01: candidates → company → thesis → journal → review → close with post-mortem; screener save/load;
// capex membership confirm (the allowlist login is e2e/auth.setup.ts). One seeded world, so the steps run in order.
test.describe.configure({ mode: "serial" });

async function flash(page: Page, text: string | RegExp): Promise<void> {
  await expect(page.getByRole("main").getByRole("status")).toContainText(text);
}

async function journalEntry(page: Page, action: string, reason: string, override?: string): Promise<void> {
  await page.getByLabel("Action").selectOption(action);
  await page.getByLabel("Reason", { exact: true }).fill(reason);
  if (override !== undefined) await page.getByLabel(/^Override reason/).fill(override);
  await page.getByRole("button", { name: "Add entry" }).click();
}

test("candidates: dismiss one with a reason, start research on another", async ({ page }) => {
  await page.goto("/candidates");
  await expect(page.getByRole("heading", { level: 1, name: "Candidates" })).toBeVisible();
  const kappa = page.getByRole("row").filter({ hasText: "Kappa Cables Ltd" });
  await kappa.locator("summary").click();
  await kappa.getByLabel("Reason").fill("Promoter pledge is rising");
  await kappa.getByRole("button", { name: "Dismiss for this week", exact: true }).click();
  await flash(page, "Dismissed for this week.");
  await expect(page.getByRole("row").filter({ hasText: "Kappa Cables Ltd" })).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "Echo Grid Corp." })).toHaveCount(1);

  await page.getByRole("link", { name: "Early" }).click();
  await page.getByRole("row").filter({ hasText: "Delta Power Inc." }).getByRole("button", { name: "Research" }).click();
  await expect(page).toHaveURL(/\/theses\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Delta Power Inc.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Research");
  await expect(page.getByText("No card yet")).toBeVisible();
});

test("company → thesis → journal → review → close with a post-mortem", async ({ page }) => {
  await page.goto("/candidates");
  await page.getByRole("link", { name: "Echo Grid Corp." }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Echo Grid Corp. (ECHO)");
  await expect(page.getByText("Revenue (TTM)")).toBeVisible();
  await expect(page.getByText("Total backlog reached $13.2 billion at quarter end.")).toBeVisible();

  await page.getByRole("link", { name: /Research · week 2026-09-18 · routine/ }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Card" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Why it may be mispriced" })).toBeVisible();
  await page.getByRole("button", { name: "Accept as thesis" }).click();
  await flash(page, "Accepted");
  // the quarter ended 2026-06-30 was filed after the card's pack: the page creates its review (§4.9)
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Review");
  await expect(page.getByText("waiting for a verdict")).toBeVisible();

  await journalEntry(page, "start_position", "Backlog converts; the price implies 5% growth.");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("week(s) old; the rule is 4");
  await journalEntry(page, "start_position", "Backlog converts; the price implies 5% growth.", "Order book confirmed.");
  await flash(page, "Position recorded in the journal.");

  await page.getByLabel("intact", { exact: true }).check();
  await page.getByLabel("Note", { exact: true }).fill("Q2 in line with the card.");
  await page.getByLabel("Also add the note to the journal").check();
  await page.getByRole("button", { name: "Record verdict" }).click();
  await flash(page, "Marked intact.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Position");

  await journalEntry(page, "exit", "The thesis played out.");
  await flash(page, "Journal entry added.");

  await page.getByLabel("What happened, compared with the thesis").fill("Backlog converted as expected.");
  await page.getByLabel("yes", { exact: true }).check();
  await page.getByLabel("What the signals said").fill("S1 and S9 fired early.");
  await page.getByLabel("Lessons").fill("Wait for the second quarter of conversion.");
  await page.getByRole("button", { name: "Close thesis" }).click();
  await flash(page, "Closed with a post-mortem.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Closed");
  await expect(page.getByRole("heading", { name: "Post-mortem" })).toBeVisible();

  await page.getByRole("link", { name: "Journal" }).first().click();
  const entries = page.getByRole("region", { name: "Journal entries" });
  for (const action of ["start_position", "review", "exit"]) await expect(entries.getByRole("cell", { name: action, exact: true })).toHaveCount(1);
  await expect(page.getByText("Backlog converted as expected.")).toBeVisible();
});

test("screener: save a screen, load it, export CSV", async ({ page }) => {
  await page.goto("/screener");
  await page.getByLabel("Min Evidence (0–100)").fill("60");
  await page.getByRole("button", { name: "Run screen" }).click();
  await expect(page.getByRole("heading", { name: "Results (3)" })).toBeVisible();
  await page.getByLabel("Save as").fill("e2e evidence 60");
  await page.getByRole("button", { name: "Save screen" }).click();
  await flash(page, 'Saved "e2e evidence 60".');

  await page.goto("/screener");
  await expect(page.getByRole("heading", { name: /Results/ })).toHaveCount(0);
  await page.getByRole("link", { name: "e2e evidence 60" }).click();
  await expect(page.getByRole("heading", { name: "Results (3)" })).toBeVisible();
  await expect(page.getByText("loaded", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Min Evidence (0–100)")).toHaveValue("60");

  const csv = await page.request.get("/screener/export?min_evidence=60");
  expect(csv.ok()).toBe(true);
  expect(csv.headers()["content-type"]).toContain("text/csv");
  expect(await csv.text()).toContain("Echo Grid Corp.");
});

test("capex desk: confirm a membership", async ({ page }) => {
  await page.goto("/capex");
  await expect(page.getByRole("heading", { name: "Memberships waiting for a decision (1)" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm Kappa Cables Ltd (KAPPA) in power_equipment" }).click();
  await flash(page, "Confirmed: power_equipment.");
  await expect(page.getByRole("heading", { name: "Memberships waiting for a decision (0)" })).toBeVisible();
});

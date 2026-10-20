import { expect, test, type Page } from "@playwright/test";
import { nextFiling } from "../lib/filing";
import { OMEGA_THESIS } from "./seed";

// BRIEF §8 M7-01 (restated in overhaul PR 4): login → candidates → company → thesis → journal entry → review → close
// with a post-mortem (the allowlist login is e2e/auth.setup.ts); the Screener's and the Capex Desk's old links
// redirect. One seeded world, so the steps run in order.
test.describe.configure({ mode: "serial" });

// When a step fails, the job log shows where the page was, what it said and any browser errors (the trace is in the
// playwright-report artifact).
test.beforeEach(async ({ page }) => {
  page.on("pageerror", (e) => console.log(`[pageerror] ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") console.log(`[console.error] ${m.text()}`);
  });
});

test.afterEach(async ({ page }, info) => {
  if (info.status === info.expectedStatus) return;
  console.log(`[failed at] ${page.url()}`);
  console.log(`[page text] ${(await page.locator("body").innerText().catch(() => "")).slice(0, 1500)}`);
});

/** A company's card on the Candidates screen (one list item per company). */
function card(page: Page, name: string) {
  return page.getByRole("list", { name: "Candidates" }).getByRole("listitem").filter({ hasText: name });
}

async function flash(page: Page, text: string | RegExp): Promise<void> {
  await expect(page.getByRole("main").getByRole("status")).toContainText(text);
}

/** Opens a form that sits behind its button (a <details> whose summary reads `name`), unless it is open already. */
async function openForm(page: Page, name: string): Promise<void> {
  const summary = page.getByRole("main").locator("summary", { hasText: name });
  if ((await summary.locator("xpath=..").getAttribute("open")) === null) await summary.click();
}

async function journalEntry(page: Page, action: string, reason: string, override?: string): Promise<void> {
  await openForm(page, "Add a journal entry");
  await page.getByLabel("Action").selectOption(action);
  await page.getByLabel("Reason", { exact: true }).fill(reason);
  if (override !== undefined) await page.getByLabel(/^Override reason/).fill(override);
  await page.getByRole("button", { name: "Add entry" }).click();
}

test("the nav has three places and More; the Screener's and the Capex Desk's old links redirect", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });
  for (const name of ["This week", "Candidates", "Theses"]) await expect(nav.getByRole("link", { name, exact: true })).toHaveCount(1);
  await nav.locator("summary", { hasText: "More" }).click();
  for (const name of ["Journal", "Signal Lab", "Settings"]) await expect(nav.getByRole("link", { name, exact: true })).toBeVisible();
  await expect(nav.getByRole("link")).toHaveCount(6);
  await page.goto("/screener");
  await expect(page).toHaveURL(/\/candidates$/);
  await expect(page.getByRole("heading", { level: 1, name: "Candidates" })).toBeVisible();
  await page.goto("/capex");
  await expect(page).toHaveURL(/localhost:3000\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "This week" })).toBeVisible();
});

test("candidates: dismiss one with a reason, start research on another", async ({ page }) => {
  await page.goto("/candidates");
  await expect(page.getByRole("heading", { level: 1, name: "Candidates" })).toBeVisible();
  const kappa = card(page, "Kappa Cables Ltd");
  await kappa.locator("summary").click();
  await kappa.getByLabel("Reason").fill("Promoter pledge is rising");
  await kappa.getByRole("button", { name: "Confirm dismissal", exact: true }).click();
  await flash(page, "Dismissed until a new signal fires or Evidence moves 10.");
  // the dismissal holds while the evidence stays as it was (overhaul PR 4)
  await expect(card(page, "Kappa Cables Ltd")).toHaveCount(0);
  await expect(card(page, "Echo Grid Corp.")).toHaveCount(1);
  await page.goto("/candidates?dismissed=1");
  await expect(card(page, "Kappa Cables Ltd").getByText("dismissed", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Early" }).click();
  await card(page, "Delta Power Inc.").getByRole("button", { name: "Research" }).click();
  await expect(page).toHaveURL(/\/theses\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Delta Power Inc.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Research");
  await expect(page.getByText("No card yet")).toBeVisible();
  // a manual research entry has no validated card, so it can't become a thesis (M7 review R1-F2)
  await expect(page.getByRole("button", { name: "Accept as thesis" })).toHaveCount(0);
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
  // accept keeps the card's filing window: the one after the pack's quarter, 2026-03-31 (M7 review R2-F4)
  await expect(page.getByText("next review 2026-08-14")).toBeVisible();
  // the quarter ended 2026-06-30 was filed after the card's pack: the page creates its review (§4.9)
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Review");
  await expect(page.getByText("waiting for a verdict")).toBeVisible();
  // the pack diff since the card (M7 review R1-F4): the quarter's figures and the kill criteria before -> now
  await expect(page.getByRole("region", { name: "Figures for review 2026-06-30" })).toContainText("1.16B → 1.22B");
  await expect(page.getByRole("region", { name: "Kill criteria for review 2026-06-30" })).toContainText("m:revenue_ttm_yoy");
  // red flags from the scored week: R1 fired the two weeks before and is clear now (M7 review R2-F1)
  await expect(page.getByText(/Red flags: started none; stopped none/)).toBeVisible();
  // a fact about the June quarter published after the card's week (M7 review R2-F2)
  await expect(page.getByText(/New fact \(as of 2026-06-30, published 2026-09-21\): backlog 14\.00B/)).toBeVisible();

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
  // the next review is the filing window after the reviewed quarter (M7 review R1-F3), not the card's (R2-F4)
  const next = nextFiling("us", "1231", "2026-06-30", new Date().toISOString().slice(0, 10));
  expect(next?.closes).not.toBe("2026-08-14");
  await expect(page.getByText(`next review ${next?.closes}`)).toBeVisible();

  await journalEntry(page, "exit", "The thesis played out.");
  await flash(page, "Journal entry added.");

  await openForm(page, "Close with a post-mortem");
  await page.getByLabel("What happened, compared with the thesis").fill("Backlog converted as expected.");
  await page.getByLabel("yes", { exact: true }).check();
  await page.getByLabel("What the signals said").fill("S1 and S9 fired early.");
  await page.getByLabel("Lessons").fill("Wait for the second quarter of conversion.");
  await page.getByRole("button", { name: "Close thesis" }).click();
  await flash(page, "Closed with a post-mortem.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Closed");
  await expect(page.getByRole("heading", { name: "Post-mortem" })).toBeVisible();

  await page.goto("/journal");
  const echo = page.getByRole("region", { name: "Journal entries" }).getByRole("row").filter({ hasText: "Echo Grid Corp." });
  for (const action of ["Start position", "Review", "Exit"]) await expect(echo.getByRole("cell", { name: action, exact: true })).toHaveCount(1);
  await expect(page.getByText("Backlog converted as expected.")).toBeVisible();
});

test("a thesis moved to Review by a kill criterion gets a verdict (M7 review R1-F1)", async ({ page }) => {
  await page.goto(`/theses/${OMEGA_THESIS}`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Review");
  await expect(page.getByText("A kill criterion triggered")).toBeVisible();
  await expect(page.getByRole("region", { name: /^Kill criteria for review / })).toContainText("m:evidence");
  await page.getByLabel("intact", { exact: true }).check();
  await page.getByRole("button", { name: "Record verdict" }).click();
  await flash(page, "Marked intact.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Thesis");
});


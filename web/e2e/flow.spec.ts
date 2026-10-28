import { expect, test, type Page } from "@playwright/test";
import { shortDate } from "../lib/dates";
import { nextFiling } from "../lib/filing";
import { ECHO, OMEGA_THESIS, SIGMA } from "./seed";

// BRIEF §8 M7-01 (restated in overhaul PR 4): login → candidates → company → thesis → journal entry → review → close
// with a post-mortem (the allowlist login is e2e/auth.setup.ts); the Screener's and the Capex Desk's old links
// redirect. Overhaul PR 5: Home's funnel, To do and What changed from the seeded digest; search → company → Research →
// "Card queued". One seeded world, so the steps run in order.
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
  const summary = page.getByRole("main").locator("summary", { hasText: name }).first();
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

test("Home: the funnel strip, To do live from the theses and What changed from the seeded digest (overhaul PR 5, drawn in PR 6)", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "This week" })).toBeVisible();
  // the digest's week, and one line that leads with the answer: nothing new, one candidate per market on the board
  await expect(page.getByText("Week 38 · Sep 14–18")).toBeVisible();
  await expect(page.getByRole("main")).toContainText("A quiet week: nothing new cleared the bar. Two ideas are still worth your time.");
  // the funnel: the markets' lines added up into four numbers and one insight; the digest's own lines under Details
  const funnel = page.getByRole("region", { name: "From 5 companies to 2 ideas" });
  await expect(funnel).toContainText("1 of 5 shows only one kind of signal, so its score stops at 55.");
  await expect(funnel).toContainText("US 4 → stage 4 → candidates 1 → new 0 · 1 of 4 fire one family, capped at 55");
  // To do is the Theses screen's Needs you group: the card to decide (ECHO) and the thesis in review (OMEGA)
  const todo = page.getByRole("region", { name: /^To do/ });
  await expect(todo.getByRole("link", { name: "Echo Grid Corp. (ECHO)" })).toBeVisible();
  await expect(todo.getByRole("link", { name: "Omega Systems Inc. (OMGA)" })).toBeVisible();
  // What changed: each line in plain words with its Evidence on the right, linked to the company on this site
  // whatever host the digest was written for
  const changed = page.getByRole("region", { name: "What changed" });
  const echo = changed.getByRole("listitem").filter({ hasText: "ECHO" });
  await expect(echo).toContainText("joined the board");
  // rounded as the ring and To do round it (the digest's 72.5 stays in the row's tooltip; PR 6 final review HC-1)
  await expect(echo).toContainText("Evidence 73");
  await expect(echo).toHaveAttribute("title", /Evidence 72\.5/);
  await expect(changed.getByRole("link", { name: "ECHO" })).toHaveAttribute("href", `/company/${ECHO}`);
  // On the board: the latest scored week's Candidate bucket, each with its Evidence ring
  const board = page.getByRole("region", { name: "On the board" });
  await expect(board.getByRole("link", { name: /ECHO Echo Grid Corp\./ })).toHaveAttribute("href", `/company/${ECHO}`);
  await expect(board.getByRole("img", { name: "Evidence 73 of 100" })).toBeVisible();
  // the digest's To do and Health sections (the minutes line among them) are not repeated here
  await expect(page.getByText(/Cards to accept or dismiss: \d/)).toHaveCount(0);
  await expect(page.getByText(/Actions: 812 of 2,000/)).toHaveCount(0);
  // Data health and the stale-data line: twelvedata is seeded stale, named as its row is ("Weekly prices") with its
  // provider; whether SEC is late too depends on today's date ("SEC filings and weekly prices ..." once it is), so the
  // line is read in two parts, the name in either case (PR 6 review ci-CI-1)
  const health = page.getByRole("region", { name: "Data health" });
  await expect(health).toContainText(/weekly prices \(Twelve Data\)/i);
  await expect(health).toContainText(/(is|are) out of date/);
});

test("the theme button cycles Auto, Light, Dark and back, and the server writes the choice before the first paint (PR 6 review design-F8)", async ({ page }) => {
  await page.goto("/");
  const html = page.locator("html");
  const button = page.getByRole("button", { name: /^Theme:/ });
  /** The theme the server wrote on <html> for this browser's cookie, read from the HTML it sends (no script). */
  const served = async () => /<html[^>]*\sdata-theme="(light|dark)"/.exec(await (await page.request.get("/")).text())?.[1] ?? "auto";
  await expect(html).not.toHaveAttribute("data-theme");
  await expect(button).toHaveAccessibleName("Theme: Auto (follows your device)");
  await button.click();
  await expect(html).toHaveAttribute("data-theme", "light");
  expect(await served()).toBe("light");
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "light");
  await expect(button).toHaveAccessibleName("Theme: Light");
  await button.click();
  await expect(html).toHaveAttribute("data-theme", "dark");
  expect(await served()).toBe("dark");
  await button.click();
  await expect(html).not.toHaveAttribute("data-theme");
  expect(await served()).toBe("auto");
  await page.reload();
  await expect(html).not.toHaveAttribute("data-theme");
});

test("candidates: dismiss one with a reason, start research on another", async ({ page }) => {
  await page.goto("/candidates");
  await expect(page.getByRole("heading", { level: 1, name: "Candidates" })).toBeVisible();
  // the NEW badge (overhaul PR 4): ECHO is in Candidate for the first time in 12 weeks
  await expect(card(page, "Echo Grid Corp.").getByText("NEW", { exact: true })).toBeVisible();
  // the card (overhaul PR 6): the two rings, and why it's here in plain words with the signal's code in the tooltip
  const echo = card(page, "Echo Grid Corp.");
  await expect(echo.getByRole("img", { name: "Evidence 73 of 100" })).toBeVisible();
  await expect(echo.getByRole("img", { name: "Gap 61 of 100" })).toBeVisible();
  await expect(echo.getByText("Order book growing faster than sales")).toHaveAttribute("title", "S1 Order-book acceleration");
  const kappa = card(page, "Kappa Cables Ltd");
  await kappa.locator("summary").click();
  await kappa.getByLabel("Reason").fill("Promoter pledge is rising");
  await kappa.getByRole("button", { name: "Confirm dismissal", exact: true }).click();
  await flash(page, "Dismissed until a new signal fires or Evidence moves 10.");
  // the dismissal holds while the evidence stays as it was (overhaul PR 4)
  await expect(card(page, "Kappa Cables Ltd")).toHaveCount(0);
  await expect(card(page, "Echo Grid Corp.")).toHaveCount(1);
  // Home's On the board leaves it out too, and counts what Candidates shows (PR 6 review ci-BEH-1)
  await page.goto("/");
  const board = page.getByRole("region", { name: "On the board" });
  await expect(board.getByRole("link", { name: /Echo Grid Corp\./ })).toHaveCount(1);
  await expect(board.getByRole("link", { name: /Kappa Cables Ltd/ })).toHaveCount(0);
  await expect(board.getByRole("link", { name: "All 1 on the board" })).toBeVisible();
  // and says what it left out, so the headline's and the funnel's count (the digest's 2) adds up (PR 6 final review DT-3)
  await expect(board).toContainText("1 dismissed until the evidence changes");
  await expect(board.getByRole("link", { name: "show dismissed names" })).toHaveAttribute("href", "/candidates?dismissed=1");
  await page.goto("/candidates?dismissed=1");
  await expect(card(page, "Kappa Cables Ltd").getByText("dismissed", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Early" }).click();
  await card(page, "Delta Power Inc.").getByRole("button", { name: "Research" }).click();
  await expect(page).toHaveURL(/\/theses\/[0-9a-f-]{36}\?ok=/);
  await flash(page, "Card queued for Sunday's routine.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Delta Power Inc.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Research");
  await expect(page.getByText("No card yet")).toBeVisible();
  // a manual research entry has no validated card until the routine fills it, so it can't become a thesis yet (M7
  // review R1-F2)
  await expect(page.getByRole("button", { name: "Accept as thesis" })).toHaveCount(0);
});

test("a board per market and the Watch tab (docs/SPEC_ISSUES.md 56)", async ({ page }) => {
  // with dismissed names shown, so the test above dismissing KAPPA changes nothing here
  await page.goto("/candidates?dismissed=1");
  // Both: the US's board, then India's, each with its own count; the switch counts each market
  const markets = page.getByRole("group", { name: "Markets" });
  await expect(markets.getByRole("link", { name: /^Both/ })).toHaveAttribute("aria-current", "page");
  // a card's own lists (its signal chips) aren't cards: count the list's own items
  await expect(page.getByRole("list", { name: "Candidates in the US" }).locator(":scope > li")).toHaveCount(1);
  await expect(page.getByRole("list", { name: "Candidates in India" }).locator(":scope > li")).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 2, name: /^US/ })).toBeVisible();
  await markets.getByRole("link", { name: /^India/ }).click();
  await expect(page).toHaveURL(/market=in/);
  await expect(card(page, "Kappa Cables Ltd")).toHaveCount(1);
  await expect(card(page, "Echo Grid Corp.")).toHaveCount(0);
  // Watch: each market's one-family names at full strength, the market kept
  await page.getByRole("group", { name: "Buckets" }).getByRole("link", { name: /^Watch/ }).click();
  await expect(page).toHaveURL(/bucket=watch/);
  await expect(page).toHaveURL(/market=in/);
  await expect(page.getByRole("main")).toContainText("One kind of evidence at full strength");
  const tara = card(page, "Tara Pumps Ltd");
  await expect(tara).toHaveCount(1);
  await expect(tara.getByRole("img", { name: "Gap 69 of 100" })).toBeVisible();
  await expect(card(page, "Lumen Water Co.")).toHaveCount(0);
  await page.getByRole("group", { name: "Markets" }).getByRole("link", { name: /^Both/ }).click();
  await expect(page.getByRole("list", { name: "Candidates in the US" }).getByRole("listitem").filter({ hasText: "Lumen Water Co." })).toHaveCount(1);
  // Home: On the board and Watch, each per market
  await page.goto("/");
  const watch = page.getByRole("region", { name: "Watch" });
  await expect(watch.getByRole("list", { name: "US" }).getByRole("link", { name: /LMNW Lumen Water Co\./ })).toBeVisible();
  await expect(watch.getByRole("list", { name: "India" }).getByRole("link", { name: /TARAPUMP Tara Pumps Ltd/ })).toBeVisible();
  await expect(watch.getByRole("link", { name: "All 2 on Watch" })).toHaveAttribute("href", "/candidates?bucket=watch");
  const board = page.getByRole("region", { name: "On the board" });
  await expect(board.getByRole("list", { name: "US" }).getByRole("link", { name: /ECHO Echo Grid Corp\./ })).toBeVisible();
});

test("search → company → Research → 'Card queued' (overhaul PR 5)", async ({ page }) => {
  await page.goto("/candidates");
  await page.waitForLoadState("networkidle"); // the "/" shortcut listens once the page is hydrated
  const box = page.getByRole("searchbox", { name: "Search companies" });
  await page.keyboard.press("/");
  await expect(box).toBeFocused();
  // a name match lists the companies with market, bucket and Evidence
  await box.fill("Grid Corp");
  await box.press("Enter");
  await expect(page).toHaveURL(/\/search\?q=Grid\+Corp$/);
  await expect(box).toHaveValue("Grid Corp"); // the query stays in the box, to refine it (PR 6 final review L5-15)
  const results = page.getByRole("list", { name: "Search results" }); // one row per company (overhaul PR 6)
  await expect(results.getByRole("listitem").filter({ hasText: "Echo Grid Corp." })).toContainText("On the board"); // the Candidate bucket
  // "/" types a slash inside a field instead of jumping
  await box.fill("a");
  await box.press("/");
  await expect(box).toHaveValue("a/");
  // anything but letters, digits, spaces and . & - is turned away with a plain message
  await box.fill("50%_off");
  await box.press("Enter");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("letters, digits, spaces and . & - only");
  // an exact ticker opens the Company page; SIGMA's only thesis is closed, so it offers Research
  await box.fill("sgma");
  await box.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/company/${SIGMA}$`));
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Sigma Holdings Inc. (SGMA)");
  await expect(page.getByRole("heading", { level: 2, name: "Why this score" })).toBeVisible();
  await expect(page.getByText("hard: excludes the company")).toBeVisible(); // R3, an auditor change
  await page.getByRole("main").getByRole("button", { name: "Research" }).click();
  await expect(page).toHaveURL(/\/theses\/[0-9a-f-]{36}\?ok=/);
  await flash(page, "Card queued for Sunday's routine.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Sigma Holdings Inc.");
  // the entry is live now: the Company page opens it instead of starting another
  await page.goto(`/company/${SIGMA}`);
  await expect(page.getByRole("main").getByRole("link", { name: "Open research card" })).toBeVisible();
  await expect(page.getByRole("main").getByRole("button", { name: "Research" })).toHaveCount(0);
});

test("company → thesis → journal → review → close with a post-mortem", async ({ page }) => {
  await page.goto("/candidates");
  await page.getByRole("link", { name: "Echo Grid Corp." }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Echo Grid Corp. (ECHO)");
  // Why this score (overhaul PR 5): the families, each fired signal's firing since and Lab verdict, the Gap's parts
  const why = page.getByRole("region", { name: "Why this score" });
  await expect(why).toContainText("2 families fired (Fundamentals, Text), so the one-family cap at 55 does not apply.");
  await expect(why).toContainText("S1 Order-book acceleration");
  await expect(why).toContainText("firing since 2026-09-11");
  await expect(why).toContainText("unproven"); // S1's out-of-sample t is 1.1
  await expect(why).toContainText("not testable yet"); // S9
  await expect(why).toContainText("Implied growth (g*)"); // C2's reverse DCF, folded in
  // drawn (overhaul PR 6): the rings in the header, each signal's Lab verdict as a chip, the live card's kill criteria
  // as a checklist and the insiders' buying as bars; the codes and workings above sit behind Why and Details
  await expect(page.getByRole("main").getByRole("img", { name: "Evidence 73 of 100" })).toBeVisible();
  await expect(why.getByText("Lab: unproven")).toBeVisible();
  const kill = page.getByRole("region", { name: "What would kill it" });
  await expect(kill).toContainText("TTM revenue growth under 5.0%");
  await expect(kill).toContainText("Now 24.0% · safe");
  // checked every week from the criterion's check_after date on, the same line the Thesis page says (PR 6 final review EYE2-1)
  await expect(kill).toContainText("Checked after Nov 20");
  await expect(page.getByRole("region", { name: "Insiders bought" })).toContainText("$510K");
  await expect(page.getByText("Revenue (TTM)")).toBeVisible();
  // the verified facts are folded under their count (a card's citation opens them: components/open-target.tsx)
  const facts = page.getByRole("region", { name: "Verified facts" });
  await facts.locator("summary", { hasText: "Show the quotes" }).click();
  await expect(facts.getByText("Total backlog reached $13.2 billion at quarter end.")).toBeVisible();

  await page.getByRole("main").getByRole("link", { name: "Open research card" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Card" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Why it may be mispriced" })).toBeVisible();
  await page.getByRole("button", { name: "Accept as thesis" }).click();
  await flash(page, "Accepted");
  // each header chip reads as one run of words, the date and its comma together (as rendered: innerText splits a
  // chip's flex items apart; PR 6 final review V4-4)
  const stands = page.getByRole("list", { name: "Where it stands" });
  await expect(stands).toContainText(/Accepted [A-Z][a-z]{2} \d{1,2}, \d{4}, (this week|\d+ weeks? ago)/, { useInnerText: true });
  await expect(stands).toContainText(/Kill criteria: \d+ of \d+ triggered/, { useInnerText: true });
  await expect(stands).toContainText(/Card of Sep 18, 2026/, { useInnerText: true });
  const thesisKill = page.getByRole("region", { name: "What would kill it" });
  await expect(thesisKill).toContainText("Checked after Nov 20"); // as the Company page says it (PR 6 final review EYE2-1)
  await expect(thesisKill).not.toContainText("each filing");
  // accept keeps the card's filing window: the one after the pack's quarter, 2026-03-31 (M7 review R2-F4); dates read
  // as the screens say them (PR 6 review design-F6)
  await expect(page.getByText("next review Aug 14, 2026")).toBeVisible();
  // the quarter ended 2026-06-30 was filed after the card's pack: the page creates its review (§4.9)
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Review");
  await expect(page.getByText("waiting for a verdict")).toBeVisible();
  // the pack diff since the card (M7 review R1-F4): the quarter's figures and the kill criteria before -> now
  await expect(page.getByRole("region", { name: "Figures for review 2026-06-30" })).toContainText("1.16B → 1.22B");
  const killThen = page.getByRole("region", { name: "Kill criteria for review 2026-06-30" });
  await expect(killThen).toContainText("TTM revenue growth under 5.0%");
  // in the metric's unit, as the checklist beside it says it, not as a raw fraction (PR 6 final review V4-2)
  await expect(killThen).toContainText(/ → 24\.0%/);
  // red flags from the scored week: R1 fired the two weeks before and is clear now, so nothing shows as a new red flag
  // (M7 review R2-F1); only what changed is listed (PR 6 final review V4-9)
  await expect(page.getByText("No signal or red flag changes.")).toBeVisible();
  await expect(page.getByText(/New red flags:/)).toHaveCount(0);
  // a fact about the June quarter published after the card's week (M7 review R2-F2), its money in its currency
  // (docs/SPEC_ISSUES.md 58)
  await expect(page.getByText(/New fact \(as of Jun 30, 2026, published Sep 21, 2026\): backlog \$14B/)).toBeVisible();

  await journalEntry(page, "start_position", "Backlog converts; the price implies 5% growth.");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("week(s) old; the rule is 4");
  await journalEntry(page, "start_position", "Backlog converts; the price implies 5% growth.", "Order book confirmed.");
  await flash(page, "Position recorded in the journal.");

  await openForm(page, "Record a verdict");
  await page.getByLabel("intact", { exact: true }).check();
  await page.getByLabel("Note", { exact: true }).fill("Q2 in line with the card.");
  await page.getByLabel("Also add the note to the journal").check();
  await page.getByRole("button", { name: "Record verdict" }).click();
  await flash(page, "Marked intact.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Position");
  // the next review is the filing window after the reviewed quarter (M7 review R1-F3), not the card's (R2-F4)
  const next = nextFiling("us", "1231", "2026-06-30", new Date().toISOString().slice(0, 10));
  expect(next?.closes).not.toBe("2026-08-14");
  await expect(page.getByText(`next review ${shortDate(next?.closes ?? "", true)}`)).toBeVisible();

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
  // one row per entry, led by its action (overhaul PR 6)
  const echo = page.getByRole("list", { name: "Journal entries" }).getByRole("listitem").filter({ hasText: "Echo Grid Corp." });
  for (const action of ["Start position", "Review", "Exit"]) await expect(echo.getByText(action, { exact: true })).toHaveCount(1);
  await expect(page.getByText("Backlog converted as expected.")).toBeVisible();
});

test("a thesis moved to Review by a kill criterion gets a verdict (M7 review R1-F1)", async ({ page }) => {
  await page.goto(`/theses/${OMEGA_THESIS}`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Review");
  await expect(page.getByText("A kill criterion triggered")).toBeVisible();
  await expect(page.getByRole("region", { name: /^Kill criteria for review / })).toContainText("Evidence score under 80");
  await expect(page.getByRole("region", { name: /^Kill criteria for review / })).toContainText("82 → 66"); // whole scores (PR 6 final review V4-2)
  // the Evidence score is checked weekly from check_after, not with filings (PR 6 final review EYE2-1)
  await expect(page.getByRole("region", { name: "What would kill it" })).toContainText("Checked after Sep 1");
  await openForm(page, "Record a verdict");
  await page.getByLabel("intact", { exact: true }).check();
  await page.getByRole("button", { name: "Record verdict" }).click();
  await flash(page, "Marked intact.");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Thesis");
});


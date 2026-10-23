import { describe, expect, it } from "vitest";
import { pickSection } from "@/lib/cards";
import type { SourceHealth, Thesis } from "@/lib/data";
import {
  boardWhy,
  boardWhyAll,
  changeItems,
  comingUp,
  countWord,
  describeChange,
  funnelInsight,
  funnelSteps,
  funnelTitle,
  funnelTotals,
  funnelWidth,
  headline,
  healthRows,
  homeSections,
  lateLine,
  leftBucket,
  localLinks,
  midSentence,
  parseFunnel,
  pluralSource,
  shownDelta,
  todoAsk,
  todoMinutes,
} from "@/lib/home";

// Overhaul PR 5: Home shows the digest's "## This week" (the funnel) and "## What changed" sections of body_md as
// pipeline/digest/weekly.py writes them; To do comes live from the database and Health is Home's own Data health
// (overhaul PR 6), so neither of those sections is shown. BODY is tests/digest/snapshots/digest_2026-W38.md with the minutes line of
// tests/digest/test_weekly_body.py.

const ECHO = "00000000-0000-4000-8000-0000000000e1";
const KAPPA = "00000000-0000-4000-8000-0000000000e2";
const BODY = `Week ending 2026-09-18. Research only: no orders, no price alerts.

## This week

US 1 → stage 1 → candidates 1 → new 1 · 0 of 1 fire one family, capped at 55

IN 1 → stage 1 → candidates 1 → new 1 · 0 of 1 fire one family, capped at 55

## To do

- Theses in review: 1 (Kappa Cables (KAPPA))

## What changed

- [ECHO](https://doomberg.example/company/${ECHO}) new candidate (#1): S1 fired (fundamentals, text), Evidence 72.5, Gap 58.3
- [KAPPA](https://doomberg.example/company/${KAPPA}) new candidate (#2): S1 fired (fundamentals, text), Evidence 64, Gap 58.3

## Health

**Stale data:** twelvedata (no success for 11 days; SLA 8). Signals and scores that read these sources may be out of date.

Actions: 812 of 2,000 this cycle, projected 1,340.
`;

describe("Home's cut of the digest", () => {
  it("takes the funnel paragraphs from This week and the lines of What changed, not To do or Health", () => {
    const s = homeSections(BODY);
    expect(s.funnel).toBe(
      "US 1 → stage 1 → candidates 1 → new 1 · 0 of 1 fire one family, capped at 55\n\n" +
        "IN 1 → stage 1 → candidates 1 → new 1 · 0 of 1 fire one family, capped at 55",
    );
    expect(s.changed).toBe(
      `- [ECHO](/company/${ECHO}) new candidate (#1): S1 fired (fundamentals, text), Evidence 72.5, Gap 58.3\n` +
        `- [KAPPA](/company/${KAPPA}) new candidate (#2): S1 fired (fundamentals, text), Evidence 64, Gap 58.3`,
    );
    for (const gone of ["Theses in review", "Stale data", "Actions:"]) expect(s.funnel + s.changed).not.toContain(gone);
  });

  it("ends a section at the next ## heading", () => {
    expect(pickSection(BODY, "To do")).toBe("- Theses in review: 1 (Kappa Cables (KAPPA))");
    expect(pickSection(BODY, "Health")).toContain("Actions: 812 of 2,000");
    expect(pickSection("## What changed\n- a\n### Detail\n- b\n## Health\n- c", "What changed")).toBe("- a\n### Detail\n- b");
  });

  it("shows a quiet week's and an unscored week's sentences", () => {
    const quiet = "## This week\n\nUS 4,659 → stage 456 → candidates 0 → new 0 · 440 of 456 fire one family, capped at 55\n\n" +
      "## To do\n\nNothing needs you this week.\n\n## What changed\n\nNothing changed this week.\n\n## Health\n\nSources: none late or stale.\n";
    expect(homeSections(quiet).changed).toBe("Nothing changed this week.");
    const unscored = "## This week\n\n**Candidates are missing this week:** no scores were written for 2026-09-18 (the US data " +
      "run failed, so nothing was scored; see health below).\n\n## To do\n\nNothing needs you this week.\n";
    expect(homeSections(unscored).funnel).toContain("no scores were written for 2026-09-18");
  });

  it("is empty without a digest", () => {
    expect(homeSections("")).toEqual({ funnel: "", changed: "", legacy: "" });
  });

  it("shows a digest written before this format as it is, less its source and quota tables (web-WEB-2)", () => {
    const old = "# Doomberg weekly — 2026-W42\n\n## New candidates\n\n- [CELH](https://x.example/company/" +
      "00000000-0000-4000-8000-000000000001) Evidence 62\n\n## Source health\n\n| a |\n\n## LLM quota use\n\n| b |\n";
    const s = homeSections(old);
    expect([s.funnel, s.changed]).toEqual(["", ""]);
    expect(s.legacy).toContain("## New candidates");
    expect(s.legacy).toContain("[CELH](/company/00000000-0000-4000-8000-000000000001)");
    expect(s.legacy).not.toContain("Source health");
    expect(s.legacy).not.toContain("LLM quota use");
    expect(s.legacy.startsWith("# ")).toBe(false);
    expect(homeSections("## Source health\n\n| a |")).toEqual({ funnel: "", changed: "", legacy: "" });
  });

  it("opens the digest's company links on this site, and leaves other links alone", () => {
    expect(localLinks(`[A](http://localhost:3000/company/${ECHO}) [B](/company/${ECHO}) [C](https://www.sec.gov/x)`)).toBe(
      `[A](/company/${ECHO}) [B](/company/${ECHO}) [C](https://www.sec.gov/x)`,
    );
  });
});

// Overhaul PR 6 draws the same sections: the funnel line as four numbers, bars and one sentence; each What changed line
// as a row in plain words with its direction and Evidence move. The line shapes are pipeline/digest/changes.py's, as
// tests/digest/test_changes.py pins them.
describe("the funnel strip (overhaul PR 6)", () => {
  const US = "US 4,659 → stage 456 → candidates 3 → new 0 · 440 of 456 fire one family, capped at 55";

  it("reads each market's line, and nothing from a week without scores", () => {
    expect(parseFunnel(US)).toEqual([
      { market: "US", scored: 4659, stage: 456, candidates: 3, fresh: 0, oneFamily: 440, cap: "55", text: US },
    ]);
    const both = parseFunnel(homeSections(BODY).funnel);
    expect(both.map((l) => [l.market, l.scored, l.candidates, l.fresh])).toEqual([["US", 1, 1, 1], ["IN", 1, 1, 1]]);
    expect(parseFunnel("**Candidates are missing this week:** no scores were written for 2026-09-18 (x).")).toEqual([]);
  });

  it("adds the markets up and draws the bars on a log scale, as the mock does", () => {
    const t = funnelTotals(parseFunnel(US))!;
    expect(funnelSteps(t).map((s) => [s.label, s.value, s.width])).toEqual([
      ["US companies scored", 4659, 100],
      ["show real evidence", 456, 73],
      ["on the board", 3, 16],
      ["new this week", 0, 0],
    ]);
    // a phone shows the mock's one word per step (PR 6 review design-F10)
    expect(funnelSteps(t).map((s) => s.short)).toEqual(["scored", "signal", "on board", "new"]);
    const two = funnelTotals(parseFunnel(homeSections(BODY).funnel))!;
    expect([two.scored, two.candidates, funnelSteps(two)[0]!.label]).toEqual([2, 2, "companies scored"]);
    expect(funnelTotals([])).toBeNull();
    expect([funnelWidth(1, 4659), funnelWidth(5, 0)]).toEqual([8, 0]);
  });

  it("titles it, says its one insight, and leads Home with the answer", () => {
    const t = funnelTotals(parseFunnel(US))!;
    expect(funnelTitle(t)).toBe("From 4,659 companies to 3 ideas");
    expect(funnelInsight(t)).toEqual({
      lead: "440 of 456",
      rest: " show only one kind of signal, so their score stops at 55. A second kind is what lifts a name onto the board.",
    });
    expect(funnelInsight({ ...t, oneFamily: 1 })?.rest).toMatch(/^ shows only one kind of signal, so its score/);
    expect(funnelInsight({ ...t, stage: 0, oneFamily: 0 })).toBeNull();
    expect(funnelTitle({ ...t, candidates: 0 })).toBe("4,659 companies scored, none on the board");
    expect(funnelTitle({ ...t, scored: 1, candidates: 1 })).toBe("From 1 company to 1 idea");
    const say = (totals: typeof t | null, funnel = "", legacy = "") => headline({ digest: true, totals, funnel, legacy });
    expect(say(t)).toBe("A quiet week: nothing new cleared the bar. Three ideas are still worth your time.");
    expect(say({ ...t, candidates: 1 })).toBe("A quiet week: nothing new cleared the bar. One idea is still worth your time.");
    expect(say({ ...t, fresh: 2, candidates: 5 })).toBe("Two new ideas cleared the bar this week. Five on the board in all.");
    expect(say({ ...t, fresh: 1, candidates: 1 })).toBe("One new idea cleared the bar this week.");
    expect(say({ ...t, candidates: 0 })).toBe("A quiet week: nothing cleared the bar.");
    expect(say(null, "**Candidates are missing this week:** ...")).toBe("No scores this week, so the board stands as it was.");
    expect(headline({ digest: false, totals: null, funnel: "", legacy: "" })).toMatch(/^No digest yet/);
    expect([countWord(10), countWord(11), countWord(4659)]).toEqual(["Ten", "11", "4,659"]);
  });
});

describe("What changed as rows in plain words (overhaul PR 6)", () => {
  const d = (text: string) => {
    const c = describeChange(text);
    return [c.dir, c.title, c.why, c.delta ? `${c.delta.label} ${c.delta.value}` : null];
  };

  it("words each bucket change, with the Evidence move on the right", () => {
    expect(d("left Candidate: S4 stopped, Evidence 62 → 48")).toEqual(["down", "left the board", "Stopped: cash flow rising ahead of profits", "Evidence 62 → 48"]);
    expect(d("moved from Early to Candidate: S7 fired, Evidence 55 → 64")).toEqual(["up", "moved from Early to the board", "New: insiders buying shares", "Evidence 55 → 64"]);
    expect(d("moved from Candidate to Early: Gap 45")).toEqual(["down", "moved from the board to Early", "", "Gap 45"]);
    expect(d("entered Early: S7 fired, Evidence 38 → 52")).toEqual(["up", "entered Early", "New: insiders buying shares", "Evidence 38 → 52"]);
    expect(d("entered Candidate: Evidence 72.5")).toEqual(["up", "joined the board", "", "Evidence 72.5"]);
    expect(d("entered Priced-in (Gap 31): S1 fired")).toEqual(["flat", "is now priced in", "New: order book growing faster than sales", "Gap 31"]);
    expect(d("now priced in (Gap 31)")).toEqual(["flat", "is now priced in", "", "Gap 31"]);
    expect(d("left Early: R3 hard flag")).toEqual(["down", "left Early", "Red flag: auditor change, late filing or going-concern language", null]);
    expect(d("left Candidate: not scored this week")).toEqual(["down", "left the board", "Not scored this week", null]);
    expect(d("left Candidate: Gap not known this week")).toEqual(["down", "left the board", "Gap not known this week", null]);
    expect(d("left Candidate: S4 stopped, R1 soft flag, Evidence 62 → 40")[2]).toBe(
      "Stopped: cash flow rising ahead of profits · Watch out: accruals high or cash conversion weak",
    );
    expect(d("now Excluded: R3 hard flag")[0]).toBe("bad");
    expect(d("no longer Excluded: R3 cleared")[0]).toBe("up");
  });

  it("words Evidence moves, signal changes, new candidates and facts", () => {
    expect(d("Evidence 60 → 70")).toEqual(["up", "Evidence rose", "", "Evidence 60 → 70"]);
    expect(d("Evidence 60.5 → 50.5")).toEqual(["down", "Evidence fell", "", "Evidence 60.5 → 50.5"]);
    expect(d("Evidence 63 → 75: S1, S9 fired")[2]).toBe("New: order book growing faster than sales, verified wins in its filings");
    expect(d("S7 fired, Evidence 60 → 69.9")).toEqual(["up", "gained a signal", "New: insiders buying shares", "Evidence 60 → 69.9"]);
    expect(d("S2 stopped")).toEqual(["down", "lost a signal", "Stopped: returns on new investment rising", null]);
    expect(d("R2 soft flag")[0]).toBe("down");
    const top = describeChange("new candidate (#1): S1, S9 fired (fundamentals, text), Evidence 72.5, Gap 61.2");
    expect([top.dir, top.title, top.why, top.delta, top.families]).toEqual([
      "up",
      "is new on the board (#1)",
      "Order book growing faster than sales, verified wins in its filings",
      { label: "Evidence", value: "72.5" },
      ["fundamentals", "text"],
    ]);
    expect(d("new verified order win: a $600 million order from a hyperscale customer ($600.0M)")).toEqual([
      "news",
      "new verified order win",
      "a $600 million order from a hyperscale customer ($600.0M)",
      null,
    ]);
    expect(d("backlog raised: $38.0B → $45.0B (+18.4%)")).toEqual(["up", "backlog raised", "$38.0B → $45.0B (+18.4%)", null]);
    expect(d("capex guidance lowered: $2.0B → $1.5B (−25.0%)")[0]).toBe("down");
    expect(d("something new the digest learned to say")).toEqual(["flat", "something new the digest learned to say", "", null]);
  });

  it("reads the section's linked lines, keeps the line as written, and finds who left a bucket", () => {
    const items = changeItems(homeSections(BODY).changed);
    expect(items.map((c) => [c.code, c.href, c.title])).toEqual([
      ["ECHO", `/company/${ECHO}`, "is new on the board (#1)"],
      ["KAPPA", `/company/${KAPPA}`, "is new on the board (#2)"],
    ]);
    expect(items[0]!.raw).toBe("new candidate (#1): S1 fired (fundamentals, text), Evidence 72.5, Gap 58.3");
    expect(changeItems("Nothing changed this week.")).toEqual([]);
    const week = changeItems(
      `- [MTDR](/company/${ECHO}) left Candidate: S4 stopped, Evidence 62 → 48\n` +
        `- [EARL](/company/${KAPPA}) moved from Candidate to Early: Gap 45\n` +
        `- [GONE](/company/${KAPPA}) left Early: Gap 45\n` +
        `- [PRCD](/company/${KAPPA}) now priced in (Gap 31)`,
    );
    expect(leftBucket(week, "candidate").map((c) => c.code)).toEqual(["MTDR", "EARL"]);
    expect(leftBucket(week, "early").map((c) => c.code)).toEqual(["GONE"]);
    expect(leftBucket(week, "priced_in")).toEqual([]);
  });
});

describe("To do, Coming up, On the board and Data health (overhaul PR 6)", () => {
  it("asks for the decision each To do row needs", () => {
    // `short` is the phone's one line, as the phone mock's "Card ready · Evidence 94" (PR 6 final review HC-10)
    expect(todoAsk("research", { now: 72.5, kills: [] })).toEqual({
      ask: "New research card: accept it or pass · Evidence 73",
      short: "Card ready · Evidence 73",
      action: "Review card",
      alert: false,
    });
    expect(todoAsk("research")).toEqual({ ask: "New research card: accept it or pass", short: "Card ready", action: "Review card", alert: false });
    expect(todoAsk("review", { now: 66, kills: ["triggered", "ok"] })).toEqual({
      ask: "A kill check triggered: record a verdict",
      short: "Kill check triggered",
      action: "Open review",
      alert: true,
    });
    expect(todoAsk("review", { now: 66, kills: ["triggered", "triggered"] }).short).toBe("2 kill checks triggered");
    expect(todoAsk("review", { now: 66, kills: ["ok"] })).toMatchObject({ short: "New filing in", alert: false });
    expect([0, 1, 2, 3, 4].map(todoMinutes)).toEqual([0, 5, 10, 10, 15]);
  });

  it("lists each live card's next filing from today on, soonest first", () => {
    const co = (ticker: string) => ({ name: ticker, market: "us" as const, ticker, nse_symbol: null, fiscal_year_end: "1231" });
    const pack = (form: string, closes: string) => ({ next_filing: { period_end: "2026-09-30", form, opens: "2026-10-01", closes } });
    const t = (id: string, state: Thesis["state"], extra: Partial<Thesis>): Thesis =>
      ({ id, state, evidence_pack: {}, card_json: {}, next_review: null, companies: co(id.toUpperCase()), ...extra }) as Thesis;
    const list = [
      t("celh", "research", { evidence_pack: pack("10-Q", "2026-11-14"), card_json: { kill_criteria: [{}, {}, {}] } as Thesis["card_json"] }),
      t("embc", "research", { evidence_pack: pack("10-K", "2026-12-29") }),
      t("old", "research", { evidence_pack: pack("10-Q", "2026-08-14") }), // its window closed: not coming up
      t("omga", "review", { evidence_pack: pack("10-Q", "2026-08-14"), next_review: "2026-11-14" }),
      t("hhh", "thesis", { evidence_pack: pack("10-Q", "2026-11-14"), next_review: "2026-11-14" }),
      t("shut", "closed", { evidence_pack: pack("10-Q", "2026-11-14") }),
      t("none", "research", {}),
    ];
    expect(comingUp(list, "2026-10-22", new Map([["omga", 1]])).map((u) => `${u.code} ${u.what}`)).toEqual([
      "CELH 10-Q by Nov 14 · 3 kill checks",
      "HHH 10-Q by Nov 14",
      "OMGA next review Nov 14 · 1 kill check", // its next scheduled review, not a deadline (PR 6 final review DT-5)
      "EMBC 10-K by Dec 29",
    ]);
    expect(comingUp(list, "2026-10-22", new Map(), 1)).toHaveLength(1);
  });

  it("rounds What changed's Evidence as the rings and To do do, unless that hides a move (PR 6 final review HC-1)", () => {
    expect(shownDelta("72.5")).toBe("73");
    expect(shownDelta("81.5 → 45.2")).toBe("82 → 45");
    expect(shownDelta("81 → 45.5")).toBe("81 → 46");
    expect(shownDelta("64")).toBe("64");
    expect(shownDelta("58.3")).toBe("58");
    expect(shownDelta("72.6 → 72.9")).toBe("72.6 → 72.9"); // "73 → 73" would read as no move
    expect(shownDelta("n/a")).toBe("n/a");
  });

  it("says a source's name mid-sentence and knows the Data health names are plural (PR 6 final review DT-7, C8)", () => {
    expect(["Weekly prices", "SEC filings", "Fund holdings (13F)", "NSE"].map(midSentence)).toEqual([
      "weekly prices",
      "SEC filings",
      "fund holdings (13F)",
      "NSE",
    ]);
    expect(["sec", "twelvedata", "sec_13f", "nse"].map(pluralSource)).toEqual([true, true, true, false]);
  });

  it("says why a name is on the board in two signals, by the Company page's short names (PR 6 review design-F3)", () => {
    expect(boardWhy(["S7", "S4", "S9"])).toBe("Insider buying · Earnings quality");
    expect(boardWhy([])).toBe("No signal fired");
    // the row's tooltip has every fired signal in everyday words
    expect(boardWhyAll(["S7", "S4", "S9"])).toBe("Insiders buying shares · cash flow rising ahead of profits · verified wins in its filings");
    expect(boardWhyAll([])).toBe("No signal fired");
  });

  it("gives each watched source a state and a date, and the stale line", () => {
    const now = new Date("2026-09-20T00:00:00Z");
    const s = (source: string, last_success: string | null, stale = false): SourceHealth => ({ source, last_success, last_error: null, stale });
    const rows = [s("sec", "2026-09-18T06:00:00Z"), s("twelvedata", null, true), s("sec_13f", "2026-03-01T00:00:00Z"), s("yahoo", null, true)];
    expect(healthRows(rows, now)).toEqual([
      { source: "sec", name: "SEC filings", state: "ok", when: "Sep 18" },
      { source: "twelvedata", name: "Weekly prices", state: "down", when: "stale" },
      { source: "sec_13f", name: "Fund holdings (13F)", state: "late", when: "late · Mar 1" },
    ]);
    expect(healthRows([s("sec", null)], now)[0]).toMatchObject({ state: "down", when: "never" });
    // the late line names each source as its row does, with the provider the row's name leaves out (PR 6 review
    // design-F7)
    expect(lateLine(rows, now)).toBe("Weekly prices (Twelve Data) and fund holdings (13F) are out of date, so scores that read them may be behind.");
    expect(lateLine([rows[1]!], now)).toBe("Weekly prices (Twelve Data) are out of date, so scores that read them may be behind.");
    expect(lateLine([rows[0]!], now)).toBeNull();
    // the seeded e2e world after Sep 26: SEC is late too (PR 6 review ci-CI-1)
    const later = new Date("2026-10-22T00:00:00Z");
    expect(lateLine([rows[0]!, rows[1]!], later)).toBe("SEC filings and weekly prices (Twelve Data) are out of date, so scores that read them may be behind.");
  });
});

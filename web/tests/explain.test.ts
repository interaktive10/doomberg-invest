import { describe, expect, it } from "vitest";
import {
  BOARD_LABEL,
  bucketLine,
  capShort,
  cardSections,
  caseLine,
  familyWord,
  gapLine,
  INSIDER_ROWS,
  insidersCapped,
  insiderSummary,
  insiderTotal,
  KILL_SHORT,
  killName,
  killNow,
  killRule,
  latestInsiderEvents,
  money,
  pc,
  plainText,
  signalLine,
  SIGNAL_SHORT,
  signalShort,
  thesesLine,
  thesisAsk,
  trendNote,
  whenLine,
  type InsiderEvent,
} from "@/lib/explain";
import { METRIC_LABEL, SIGNAL_NAME, SIGNAL_PLAIN } from "@/lib/labels";
import { breakdown, gapParts } from "@/lib/why";
import { repoFile } from "./repo";

describe("numbers in plain words (lib/explain.ts)", () => {
  it("writes money and percentages the way people say them", () => {
    expect([money(1_830_000, "usd"), money(447_000, "USD"), money(1_050_000, "USD"), money(13_200_000_000, "USD")]).toEqual(["$1.83M", "$447K", "$1.05M", "$13.2B"]);
    expect([money(2_500_000_000, "INR"), money(1_200_000, "eur"), money(-5_000_000, "USD"), money(950, null), money(null)]).toEqual(["₹2.5B", "EUR 1.2M", "−$5M", "950", "n/a"]);
    expect([pc(0.106), pc(0.05), pc(-0.2)]).toEqual(["10.6%", "5%", "-20%"]);
  });
});

describe("the Company header's words", () => {
  it("names the buckets as the Candidates tabs do, and says what each means in one line", () => {
    expect(BOARD_LABEL.candidate).toBe("On the board");
    expect(BOARD_LABEL.priced_in).toBe("Priced in");
    expect(bucketLine("candidate")).toBe("Two kinds of evidence agree, and the price hasn't caught up yet.");
    expect(bucketLine("excluded")).toContain("hard red flag");
    expect(bucketLine(null)).toBe("Not scored yet.");
  });

  it("quotes a card's summary, else its first paragraph without the citations; nothing without a card", () => {
    expect(caseLine({ summary: " Grid demand shows up in backlog first. " }, "# T\n\nOther.")).toBe("Grid demand shows up in backlog first.");
    const md = "# Echo (ECHO) — 2026-W38\n\nBacklog leads revenue [f:00000000-0000-4000-8000-0000000000f1] by a year [c:C2].\n\n## Facts\n- x";
    expect(caseLine({}, md)).toBe("Backlog leads revenue by a year.");
    expect(caseLine(null, "# Title\n\n## Facts\n- a")).toBeNull();
    expect(caseLine({}, "- a list first")).toBeNull();
    expect(caseLine({}, "")).toBeNull();
    // pipeline/thesis/render.py leads the card with its summary: the Thesis page shows that lead once, in the header
    expect(plainText("Backlog leads revenue [f:00000000-0000-4000-8000-0000000000f1]\nby a year.")).toBe("Backlog leads revenue by a year.");
  });
});

describe("Why this score in plain words", () => {
  const W = { families: { fundamentals: 1, behavior: 1, text: 1 }, signals: { S4: 1, S7: 1, S9: 1 } };

  it("says in a few words whether the one-family cap applies", () => {
    const two = breakdown([{ signal_id: "S4", fired: true, strength: 1, inputs: null }, { signal_id: "S7", fired: true, strength: 0.89, inputs: null }], W, 0);
    expect(capShort(two)).toBe("two kinds agree, so no cap");
    const heavy = { ...W, families: { ...W.families, fundamentals: 1.5 } }; // one family alone would give 75
    const one = breakdown([{ signal_id: "S4", fired: true, strength: 1, inputs: null }, { signal_id: "S1", fired: true, strength: 1, inputs: null }], heavy, 0);
    expect(capShort(one)).toBe("one kind only, so capped at 55");
    const low = breakdown([{ signal_id: "S9", fired: true, strength: 0.4, inputs: null }], W, 1);
    expect(capShort(low)).toBe("one kind only; the cap at 55 doesn't bind; red flags take 10 off");
    expect(capShort(breakdown([], W, 0))).toBe("no signal fired");
  });

  it("names families by who or what they are", () => {
    expect([familyWord("fundamentals"), familyWord("behavior", ["S7"]), familyWord("behavior", ["S8"]), familyWord("behavior", ["S7", "S8"])]).toEqual([
      "Business",
      "Insiders",
      "Funds",
      "Insiders and funds",
    ]);
    expect([familyWord("text"), familyWord("structural"), familyWord("cycle"), familyWord("other_thing")]).toEqual(["Text facts", "Special situation", "Cycle", "Other thing"]);
  });

  it("writes one line per fired signal from its stored inputs, and falls back to its everyday description", () => {
    expect(signalShort("S4")).toBe("Earnings quality");
    expect(signalShort("S99")).toBe("S99");
    expect(signalLine("S4", { ccr: 3.94, ccr_year_ago: 1.8 })).toBe("Cash from operations is 3.9× net income, up from 1.8× a year ago.");
    expect(signalLine("S7", { insiders: 3, total_usd: "1830000", buyers: ["a", "b", "c"] })).toBe("3 insiders bought $1.83M of stock.");
    expect(signalLine("S7", { promoter_buyers: 1, total_inr: 25_000_000 })).toBe("One promoter bought ₹25M of stock.");
    expect(signalLine("S1", { gaps: [0.12, 0.08], coverage: 2.4, coverage_year_ago: 1.9 })).toBe("The order book is 2.4× a year's sales, up from 1.9× a year ago.");
    expect(signalLine("S1", { gaps: [0.12, 0.08] })).toBe("Orders grew 12 points faster than sales last quarter.");
    expect(signalLine("S3", { opm: 0.153, opm_year_ago: 0.11 })).toBe("Operating margin 15.3%, up from 11% a year ago.");
    expect(signalLine("S5", { share_change_yoy: -0.031 })).toBe("Share count down 3.1% in a year.");
    expect(signalLine("S6", { current: 1.2, past_max: 3.4 })).toBe("Net debt / EBITDA down to 1.2× from 3.4×.");
    expect(signalLine("S8", { holders: [380, 398, 412], qoq: [0.05, 0.035] })).toBe("412 funds hold it, up 3.5% in a quarter.");
    expect(signalLine("S9", { count: 1 })).toBe("One fact in its filings, checked word for word.");
    expect(signalLine("S9", { count: 3, facts: [] })).toBe("3 facts in its filings, each checked word for word.");
    expect(signalLine("S10", { events: ["spinoff:2026-03-01"], holdco: false })).toBe("A recent spinoff.");
    expect(signalLine("S12", { sector: "Utilities" })).toBe("The Utilities cycle is turning up.");
    expect(signalLine("S1", {})).toBe(SIGNAL_PLAIN.S1);
    expect(signalLine("S4", null)).toBe(SIGNAL_PLAIN.S4);
  });

  it("says what each part of the Gap found, or why it has none", () => {
    const { parts } = gapParts([
      { metric_id: "C1", value: 2.2, pct: 13, inputs: { score: 87, ev_sales: 2.2, pct_ev_sales: 13, weeks: 520 } },
      { metric_id: "C2", value: null, pct: null, inputs: { missing: ["value_creating_growth"], growth_return: 0.073 } },
      { metric_id: "C3", value: -0.54, pct: 4, inputs: { score: 96, return_52w: -0.54, population: 400, already_ran: false } },
    ]);
    expect(parts.map(gapLine)).toEqual([
      "EV/Sales 2.2: cheaper than 87% of its own history.",
      "Not scored: its growth doesn't earn more than its cost of capital.",
      "Down 54% in a year: bottom 4% of 400 names.",
    ]);
    const echo = gapParts([
      { metric_id: "C1", value: 2.8, pct: 37, inputs: { score: 63 } },
      { metric_id: "C2", value: 0.12, pct: null, inputs: { score: 80, g_star: 0.05, g_e: 0.17 } },
      { metric_id: "C3", value: 0.31, pct: 55, inputs: { score: 45 } },
    ]).parts;
    expect(echo.map(gapLine)).toEqual([
      "Its valuation against its own history.",
      "The evidence supports 17% growth; the price implies 5%.",
      "Up 31% in a year: top 45%.",
    ]);
    expect(gapLine({ id: "C1", score: 30, row: { metric_id: "C1", value: 9, pct: 70, inputs: { ev_ebit: 9, pct_ev_ebit: 70 } } })).toBe(
      "EV/EBIT 9.0: dearer than 70% of its own history.",
    );
    expect(gapLine({ id: "C3", score: null, row: null })).toBe("Not scored: not computed this week.");
    expect(gapLine({ id: "C1", score: null, row: { metric_id: "C1", value: null, pct: null, inputs: { missing: ["history", "odd_key"] } } })).toBe(
      "Not scored: not enough price history yet; odd key.",
    );
  });
});

describe("kill criteria as a checklist", () => {
  it("names the metric and the condition in a few words", () => {
    expect(killRule({ metric: "m:revenue_ttm_yoy", operator: "<", threshold: 0.05 })).toBe("TTM revenue growth under 5.0%");
    expect(killRule({ metric: "m:fcf_ttm", operator: "<=", threshold: "200000000" })).toBe("Free cash flow (TTM) at or under 200.00M");
    expect(killRule({ metric: "m:evidence", operator: "<", threshold: 80 })).toBe("Evidence score under 80");
    expect(killRule({ metric: "m:promoter_pct", operator: "changes", threshold: null, baseline: 52.5 })).toBe("Promoter holding changes from 52.5%");
    expect(Object.keys(METRIC_LABEL).filter((k) => !(k in KILL_SHORT))).toEqual([]); // every kill metric has a short name
    expect(Object.keys(SIGNAL_NAME).filter((k) => !(k in SIGNAL_SHORT))).toEqual([]); // and every signal
    expect(killName("m:signal:S7")).toBe("Insider buying signal strength");
    expect(killName("m:something_new")).toBe("Something new");
  });

  it("says where each one stands now", () => {
    expect(killNow({ metric: "m:revenue_ttm_yoy", status: "ok", last_value: 0.24 })).toBe("Now 24.0% · safe");
    expect(killNow({ metric: "m:evidence", status: "triggered", last_value: 66 })).toBe("Now 66 · triggered");
    expect(killNow({ metric: "m:roic", status: "unknown", last_value: null })).toBe("Not checked yet");
  });
});

describe("insiders as bars", () => {
  const ev = (o: Partial<InsiderEvent>): InsiderEvent => ({
    event_date: "2026-09-15",
    filed_at: "2026-09-16T20:00:00Z",
    person: "John Fieldly",
    role: "CEO",
    kind: "open_market_buy",
    value: 1_050_000,
    currency: "USD",
    planned: false,
    source_url: "https://sec.gov/a.xml",
    amends: null,
    ...o,
  });

  it("sums each person's buys in the year to the latest, most money first, and says when", () => {
    const s = insiderSummary([
      ev({}),
      ev({ person: "Damon DeSantis", role: "Director", value: 447_000, source_url: "https://sec.gov/b.xml" }),
      ev({ person: "Hal Kravitz", role: "Director", value: "336000", source_url: "https://sec.gov/c.xml", planned: true }),
      ev({ person: "Hal Kravitz", kind: "open_market_sell", value: 90_000, event_date: "2026-03-02", source_url: "https://sec.gov/d.xml" }),
      ev({ person: "Old Buyer", value: 5_000_000, event_date: "2024-01-10", source_url: "https://sec.gov/e.xml" }), // over a year before
      ev({ person: "Pledger", kind: "pledge_created", value: 9_000_000, source_url: "https://sec.gov/f.xml" }),
    ]);
    expect(s.bought?.total).toBe(1_833_000);
    expect(s.bought?.people.map((p) => [p.who, p.role, p.value])).toEqual([
      ["John Fieldly", "CEO", 1_050_000],
      ["Damon DeSantis", "Director", 447_000],
      ["Hal Kravitz", "Director", 336_000],
    ]);
    expect([s.bought?.planned, s.bought?.trades, s.bought?.currency]).toEqual([1, 3, "USD"]);
    expect(whenLine(s.bought!)).toBe("On Sep 15, 2026");
    expect(s.sold?.total).toBe(90_000);
    expect(insiderSummary([]).bought).toBeNull();
    expect(whenLine({ from: "2026-07-03", to: "2026-09-15" })).toBe("Jul 3 – Sep 15, 2026");
    expect(whenLine({ from: "2025-12-03", to: "2026-01-15" })).toBe("Dec 3, 2025 – Jan 15, 2026");
  });

  it("counts a Form 4 and its 4/A once, and an Indian disclosure's latest revision only", () => {
    const original = ev({ filed_at: "2026-09-16T20:00:00Z", source_url: "https://sec.gov/orig.xml" });
    const other = ev({ event_date: "2026-09-10", filed_at: "2026-09-16T21:00:00Z", source_url: "https://sec.gov/other.xml", value: 10 });
    const fix1 = ev({ value: 1_000_000, filed_at: "2026-09-20T15:00:00Z", source_url: "https://sec.gov/a1.xml", amends: "2026-09-16" });
    const fix2 = ev({ value: 1_100_000, filed_at: "2026-09-25T15:00:00Z", source_url: "https://sec.gov/a2.xml", amends: "2026-09-16" });
    expect(latestInsiderEvents([original, other, fix1, fix2])).toEqual([other, fix2]);
    // an amendment that corrects the trade date replaces that day's filings
    const moved = ev({ event_date: "2026-09-14", filed_at: "2026-09-21T15:00:00Z", source_url: "https://sec.gov/m.xml", amends: "2026-09-16" });
    expect(latestInsiderEvents([original, moved])).toEqual([moved]);
    // 2026-09-17 01:30 UTC is still Sep 16 on EDGAR's clock
    const late = ev({ filed_at: "2026-09-17T01:30:00Z", source_url: "https://sec.gov/late.xml" });
    expect(latestInsiderEvents([late, fix1])).toEqual([fix1]);
    const in1 = ev({ kind: "promoter_buy", filed_at: "2026-09-16T10:00:00Z", value: 100, currency: "INR", source_url: "https://bse/1" });
    const in2 = ev({ kind: "promoter_buy", filed_at: "2026-09-18T10:00:00Z", value: 120, currency: "INR", source_url: "https://bse/2" });
    expect(latestInsiderEvents([in1, in2])).toEqual([in2]);
    expect(insiderSummary([original, fix1, fix2]).bought?.total).toBe(1_100_000);
  });

  it("says 'at least' when the insiders read hit its cap (PR 6 review ci-BEH-2)", () => {
    // the cap is lib/data.ts insiders()'s limit
    const read = /export async function insiders\([^)]*\)[\s\S]*?\.limit\((\d+)\)/.exec(repoFile("web/lib/data.ts"));
    expect(Number(read?.[1])).toBe(INSIDER_ROWS);
    expect([insidersCapped(24), insidersCapped(25)]).toEqual([false, true]);
    expect(insiderTotal({ total: 510_000, currency: "USD" }, false)).toBe("$510K");
    expect(insiderTotal({ total: 1_830_000, currency: "USD" }, true)).toBe("at least $1.83M");
  });
});

describe("charts and cards", () => {
  it("says how far a chart moved in a year (four quarters)", () => {
    expect(trendNote([100, 110, 120, 130, 140, 150], "big")).toBe("+36.4% over a year");
    expect(trendNote([200, 100, 100, 100, 150], "big")).toBe("−25% over a year");
    expect(trendNote([0.1, 0.1, 0.1, 0.1, 0.131, null], "pct")).toBe("Up 3.1 points over a year");
    expect(trendNote([0.1, 0.1, 0.1, 0.1, 0.1], "pct")).toBe("Flat over a year");
    expect(trendNote([1.8, 2, 2, 2, 3.9], "x")).toBe("1.8× a year ago");
    expect(trendNote([1, 2, 3], "big")).toBeNull();
    expect(trendNote([null, 2, 3, 4, 5], "big")).toBeNull();
    expect(trendNote([-5, 2, 3, 4, 5], "big")).toBeNull();
  });

  it("cuts a card into its lead and sections, leaving out empty ones", () => {
    const md = "Backlog leads.\n\n## Facts\n- a [f:x]\n\n## Inferences\n\n## Risks\n- r\n### Sub\ntext\n";
    expect(cardSections(md)).toEqual({
      lead: "Backlog leads.",
      sections: [
        { title: "Facts", body: "- a [f:x]" },
        { title: "Risks", body: "- r\n### Sub\ntext" },
      ],
    });
    expect(cardSections("Only a lead.")).toEqual({ lead: "Only a lead.", sections: [] });
  });
});

describe("the Theses screen's words", () => {
  it("says what each row asks of you", () => {
    expect(thesisAsk({ state: "research", author: "manual", card_md: "" })).toBe("Card queued for Sunday");
    expect(thesisAsk({ state: "research", author: "routine", card_md: "# card" })).toBe("Card ready: accept it or pass");
    expect(thesisAsk({ state: "review", author: "routine", card_md: "x" })).toBe("A review waits for your verdict");
    expect(thesisAsk({ state: "position", author: "routine", card_md: "x" })).toBe("Position open");
  });

  it("leads with what needs you", () => {
    expect(thesesLine(2, 3)).toBe("2 need you, 3 being watched.");
    expect(thesesLine(1, 0)).toBe("1 needs you, 0 being watched.");
    expect(thesesLine(0, 3)).toBe("Nothing needs you; 3 being watched.");
    expect(thesesLine(0, 0)).toBe("Nothing open right now.");
  });
});

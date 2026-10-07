import { describe, expect, it } from "vitest";
import {
  ACTION_LABEL,
  BUCKET_LABEL,
  CONTEXT_NAME,
  dcfRows,
  detailText,
  FAMILY_LABEL,
  humanize,
  label,
  METRIC_LABEL,
  providerLabel,
  RED_FLAG_NAME,
  SIGNAL_NAME,
  sourceLabel,
  unitLabel,
} from "@/lib/labels";
import { BUCKETS, FAMILIES, METRICS, SIGNALS } from "@/lib/screener";
import { SLA_DAYS } from "@/lib/staleness";
import { repoFile } from "./repo";

describe("display labels (lib/labels.ts)", () => {
  it("turns stored ids into sentence case", () => {
    expect(humanize("open_market_buy")).toBe("Open market buy");
    expect(humanize("power_equipment")).toBe("Power equipment");
    expect(humanize("index-change")).toBe("Index change");
    expect(humanize("")).toBe("");
    expect(humanize(null)).toBe("");
    expect(label(BUCKET_LABEL, "priced_in")).toBe("Priced-in");
    expect(label(BUCKET_LABEL, "something_new")).toBe("Something new"); // an id the map doesn't know yet still reads
  });

  it("names every bucket, family, signal and screener metric the app uses", () => {
    for (const b of BUCKETS) expect(BUCKET_LABEL[b]).toBeTruthy();
    for (const f of FAMILIES) expect(FAMILY_LABEL[f]).toBeTruthy();
    for (const s of SIGNALS) expect(SIGNAL_NAME[s]).toBeTruthy();
    for (const m of METRICS) expect(METRIC_LABEL[m]).toBeTruthy();
    expect(Object.keys(CONTEXT_NAME)).toEqual(["C1", "C2", "C3", "C4"]);
    expect(Object.keys(RED_FLAG_NAME)).toEqual(["R1", "R2", "R3", "R4", "R5", "R6"]);
    expect(ACTION_LABEL.start_position).toBe("Start position");
    for (const s of Object.keys(SLA_DAYS)) expect(sourceLabel(s)).not.toBe(s); // every source has a proper name
  });

  it("uses BRIEF §1.4's signal names", () => {
    const brief = repoFile("docs/BRIEF.md");
    for (const [id, name] of Object.entries(SIGNAL_NAME)) {
      const row = brief.split("\n").find((l) => l.startsWith(`| ${id} | `) && l.split("|").length >= 5 && /\| (Fundamentals|Behavior|Text|Structural|Capex|Cycle) \|/.test(l));
      expect([id, row?.includes(`| ${name}:`)]).toEqual([id, true]);
    }
  });

  it("writes sources, providers and units the usual way", () => {
    expect(sourceLabel("sec_13f")).toBe("SEC 13F");
    expect(sourceLabel("stooq")).toBe("Stooq");
    expect(sourceLabel("yahoo")).toBe("Yahoo Finance");
    expect(sourceLabel("twelvedata")).toBe("Twelve Data");
    expect(sourceLabel("new_feed")).toBe("New feed");
    expect(providerLabel("openrouter")).toBe("OpenRouter");
    expect(unitLabel("usd")).toBe("USD");
    expect(unitLabel("inr")).toBe("INR");
    expect(unitLabel("percent")).toBe("%");
    expect(unitLabel("lead_months")).toBe("lead months");
  });

  it("shows an event's detail as text, not JSON", () => {
    expect(detailText({ index: "S&P MidCap 400" })).toBe("Index: S&P MidCap 400");
    expect(detailText({ from_auditor: "A LLP", to_auditor: "B LLP", note: null })).toBe("From auditor: A LLP · To auditor: B LLP");
    expect(detailText({ parts: { a: 1 } })).toBe("Parts: A: 1");
    expect(detailText("plain")).toBe("plain");
    expect(detailText(null)).toBe("");
  });

  it("lists the reverse DCF's inputs with names and units, known ones first", () => {
    // the keys pipeline/signals/reverse_dcf.py writes
    const rows = dcfRows({ g_star: 0.05, g_e: 0.17, margin: 0.2, s2c: 1.5, tax: 0.21, ev: 5.2e9, revenue: 4.5e9, discount: 0.09, terminal_growth: 0.025, zeta: "x" });
    expect(rows.map((r) => [r.label, r.value])).toEqual([
      ["Evidence growth (g_e)", "17.0%"],
      ["Implied growth (g*)", "5.0%"],
      ["Operating margin used", "20.0%"],
      ["Sales to capital", "1.50x"],
      ["Tax rate", "21.0%"],
      ["Discount rate", "9.0%"],
      ["Terminal growth", "2.5%"],
      ["TTM revenue", "4.50B"],
      ["Enterprise value", "5.20B"],
      ["Zeta", "x"],
    ]);
    expect(dcfRows({ g_star: null }).map((r) => r.value)).toEqual(["n/a"]); // no root: g* is null (BRIEF §4.7)
    expect(dcfRows({ discount_rate: "0.12", score: 80 }).map((r) => [r.label, r.value])).toEqual([
      ["Discount rate", "12.0%"],
      ["C2 score", "80"],
    ]);
  });
});

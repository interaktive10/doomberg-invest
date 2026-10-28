import { describe, expect, it } from "vitest";
import {
  ACTION_LABEL,
  BUCKET_LABEL,
  CONTEXT_NAME,
  dcfRows,
  detailText,
  FAMILY_LABEL,
  humanize,
  killMetric,
  killSentence,
  label,
  METRIC_LABEL,
  metricValue,
  providerLabel,
  RED_FLAG_NAME,
  SIGNAL_NAME,
  SIGNAL_PLAIN,
  sourceLabel,
  unitLabel,
} from "@/lib/labels";
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

  it("names every bucket, family, signal and context metric the app uses (no S11, no capex family, no C4)", () => {
    expect(Object.keys(BUCKET_LABEL)).toEqual(["candidate", "early", "watch", "priced_in", "excluded", "none"]);
    expect(Object.keys(FAMILY_LABEL)).toEqual(["fundamentals", "behavior", "text", "structural", "cycle"]);
    const signals = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S12"];
    expect(Object.keys(SIGNAL_NAME)).toEqual(signals);
    expect(Object.keys(SIGNAL_PLAIN)).toEqual(signals);
    expect(Object.keys(CONTEXT_NAME)).toEqual(["C1", "C2", "C3"]);
    expect(Object.keys(RED_FLAG_NAME)).toEqual(["R1", "R2", "R3", "R4", "R5", "R6"]);
    expect(ACTION_LABEL.start_position).toBe("Start position");
    for (const s of Object.keys(SLA_DAYS)) expect(sourceLabel(s)).not.toBe(s); // every source has a proper name
  });

  it("uses BRIEF §1.4's signal names", () => {
    const brief = repoFile("docs/BRIEF.md");
    for (const [id, name] of Object.entries(SIGNAL_NAME)) {
      const row = brief.split("\n").find((l) => l.startsWith(`| ${id} | `) && l.split("|").length >= 5 && /\| (Fundamentals|Behavior|Text|Structural|Cycle) \|/.test(l));
      expect([id, row?.includes(`| ${name}:`)]).toEqual([id, true]);
    }
  });

  it("writes sources, providers and units the usual way", () => {
    expect(sourceLabel("sec_13f")).toBe("SEC 13F");
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

  it("reads every kill-criteria metric (METRIC_LABEL) as one sentence, in its unit", () => {
    for (const [key, m] of Object.entries(METRIC_LABEL)) {
      const text = killSentence({ metric: `m:${key}`, operator: "<", threshold: 0.12, check_after: "2026-11-14" });
      expect([key, text]).toEqual([key, `Kill if ${m.label} falls below ${metricValue(0.12, m.unit)} (checked from 2026-11-14).`]);
      expect(text).not.toContain(key.includes("_") ? key : `m:${key}`); // the id never shows
      expect(text.match(/\. |\.$/g)).toHaveLength(1); // one sentence
    }
    expect(Object.keys(METRIC_LABEL)).toHaveLength(15);
  });

  it("words each operator, unit and the signal metrics", () => {
    const k = (metric: string, operator: string, threshold: number | null, baseline: number | null = null) =>
      killSentence({ metric, operator, threshold, baseline });
    expect(k("m:op_margin_ttm", "<", 0.12)).toBe("Kill if the TTM operating margin falls below 12.0%.");
    expect(k("m:revenue_ttm_yoy", "<=", 0)).toBe("Kill if TTM revenue growth over the TTM a year earlier falls to or below 0.0%.");
    expect(k("m:net_debt", ">", 2.5e9)).toBe("Kill if net debt (total debt minus cash) rises above 2.50B.");
    expect(k("m:inst_holders", ">=", 1340)).toBe("Kill if the number of 13F institutional holders rises to or above 1,340.");
    expect(k("m:promoter_pledged_pct", ">", 5)).toBe("Kill if the pledged share of the promoter holding rises above 5.0%.");
    expect(k("m:evidence", "<", 40)).toBe("Kill if the Evidence score falls below 40.");
    expect(k("m:evidence", "==", 0)).toBe("Kill if the Evidence score equals 0.");
    expect(k("m:rpo", "changes", null, 1.32e10)).toBe("Kill if remaining performance obligations (RPO) changes from 13.20B.");
    expect(k("m:rpo", "changes", null)).toBe("Kill if remaining performance obligations (RPO) changes from its value when the thesis was accepted.");
    expect(k("m:signal:S1", "<", 0.3)).toBe("Kill if S1's strength (Order-book acceleration) falls below 0.30.");
    expect(killMetric("m:something_new")).toEqual({ label: "Something new", unit: null });
    expect(metricValue(null, "ratio")).toBe("n/a");
  });
});

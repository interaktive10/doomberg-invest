import { describe, expect, it } from "vitest";
import { BUCKETS, csvRow, FAMILIES, METRICS, SIGNALS, specFromForm, specToQuery } from "@/lib/screener";
import { repoFile } from "./repo";

describe("screener spec (the JSON screen(spec) takes; pipeline/screener.py is the contract)", () => {
  it("mirrors pipeline/screener.py's metrics, buckets, families and signals", () => {
    const py = repoFile("pipeline/screener.py");
    const metrics = /METRICS = frozenset\(\{([\s\S]*?)\}\)/.exec(py)?.[1] ?? "";
    expect([...metrics.matchAll(/"(\w+)"/g)].map((m) => m[1]).sort()).toEqual([...METRICS].sort());
    const literal = (name: string) => [...(new RegExp(`${name} = Literal\\[([^\\]]*)\\]`).exec(py)?.[1] ?? "").matchAll(/"(\w+)"/g)].map((m) => m[1]);
    expect(literal("Bucket")).toEqual([...BUCKETS]);
    expect(literal("Family")).toEqual([...FAMILIES]);
    expect(literal("SignalId")).toEqual([...SIGNALS]);
  });

  it("builds a spec from the builder's form, leaving empty fields out", () => {
    const f = new FormData();
    f.set("market", "us");
    f.set("capex_desk", "true");
    f.append("buckets", "candidate");
    f.append("buckets", "early");
    f.set("min_evidence", "55");
    f.set("min_gap", "");
    f.set("exclude_hard_flags", "on");
    f.set("metric_0", "roic");
    f.set("op_0", ">=");
    f.set("value_0", "0.15");
    f.set("metric_1", "opm");
    f.set("op_1", ">=");
    f.set("value_1", "");
    expect(specFromForm(f)).toEqual({
      market: "us",
      capex_desk: true,
      buckets: ["candidate", "early"],
      min_evidence: 55,
      exclude_hard_flags: true,
      metrics: [{ metric: "roic", op: ">=", value: 0.15 }],
    });
  });

  it("refuses values outside the contract", () => {
    const bad = (k: string, v: string) => {
      const f = new URLSearchParams();
      f.set(k, v);
      return () => specFromForm(f);
    };
    expect(bad("market", "uk")).toThrow();
    expect(bad("min_evidence", "101")).toThrow();
    expect(bad("buckets", "moonshot")).toThrow();
    expect(bad("signals_any", "S13")).toThrow();
    expect(bad("limit", "5000")).toThrow();
  });

  it("round-trips through the query string (saved screens, links, CSV export)", () => {
    const spec = {
      market: "in" as const,
      buckets: ["candidate" as const],
      signals_any: ["S1" as const, "S9" as const],
      families_all: ["text" as const],
      min_gap: 40,
      metrics: [{ metric: "revenue_yoy" as const, op: ">" as const, value: 0.2 }],
    };
    expect(specFromForm(specToQuery(spec))).toEqual(spec);
  });

  it("spreads the metrics into CSV columns", () => {
    expect(csvRow({ name: "X", metrics: { roic: 0.2 } })).toMatchObject({ name: "X", roic: 0.2, opm: null });
  });
});

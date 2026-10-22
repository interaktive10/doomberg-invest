import { describe, expect, it } from "vitest";
import { exactMatch, likeEscape, parseSearch, rankHits, SEARCH_MAX, typingIn, type SearchHit } from "@/lib/search";

// Overhaul PR 5: the nav's company search. Its input is untrusted, so only letters, digits, spaces and . & - get
// through, at most 40 characters, with LIKE's wildcards escaped; lib/data.ts searchCompanies sends separate ilike
// filters, never an .or() string.

const hit = (id: string, name: string, ticker: string | null, nse_symbol: string | null = null): SearchHit => ({
  id, market: nse_symbol ? "in" : "us", name, ticker, nse_symbol,
}); // prettier-ignore

describe("company search", () => {
  it("lets letters, digits, spaces and . & - through, trimmed, as exact and contains patterns", () => {
    expect(parseSearch("  Procter & Gamble  ")).toEqual({ kind: "ok", q: "Procter & Gamble", exact: "Procter & Gamble", contains: "%Procter & Gamble%" });
    expect(parseSearch("BRK.B")).toEqual({ kind: "ok", q: "BRK.B", exact: "BRK.B", contains: "%BRK.B%" });
    expect(parseSearch("Coca-Cola  Co")).toMatchObject({ kind: "ok", q: "Coca-Cola Co" });
  });

  it("rejects anything else with a plain message: wildcards, quotes, commas, parentheses, PostgREST syntax", () => {
    for (const bad of ["50%", "a_b", "x,name.eq.y", "a)or(b", "o'neil", "<script>", "a*", "tab\there", "naïve", "a\\b", "x;drop"]) {
      const r = parseSearch(bad);
      expect([bad, r.kind]).toEqual([bad, "bad"]);
      if (r.kind === "bad") expect(r.message).toBe("Search with letters, digits, spaces and . & - only.");
    }
  });

  it("rejects input over 40 characters and accepts exactly 40", () => {
    expect(parseSearch("a".repeat(SEARCH_MAX))).toMatchObject({ kind: "ok" });
    expect(parseSearch("a".repeat(SEARCH_MAX + 1))).toEqual({ kind: "bad", message: "A search can be at most 40 characters long." });
    expect(parseSearch(` ${"a".repeat(SEARCH_MAX)} `)).toMatchObject({ kind: "ok" }); // the spaces around it don't count
  });

  it("treats an empty or blank query as no search", () => {
    expect(parseSearch(undefined)).toEqual({ kind: "empty" });
    expect(parseSearch("")).toEqual({ kind: "empty" });
    expect(parseSearch("    ")).toEqual({ kind: "empty" });
  });

  it("escapes % and _ (and the escape character) so they match themselves", () => {
    expect(likeEscape("50%_off")).toBe("50\\%\\_off");
    expect(likeEscape("a\\b")).toBe("a\\\\b");
    expect(likeEscape("plain")).toBe("plain");
  });

  it("opens the Company page for a single exact code match, case-insensitively, and lists otherwise", () => {
    const echo = hit("e", "Echo Grid Corp.", "ECHO");
    expect(exactMatch([echo], "echo")).toBe("e");
    expect(exactMatch([hit("k", "Kappa Cables Ltd", null, "KAPPA")], "Kappa")).toBe("k");
    expect(exactMatch([echo, echo], "ECHO")).toBe("e"); // the same company from two reads
    expect(exactMatch([echo, hit("e2", "Echo Two", "ECHO")], "ECHO")).toBeNull(); // two companies: list them
    expect(exactMatch([echo], "ECH")).toBeNull();
    expect(exactMatch([], "ECHO")).toBeNull();
  });

  it("ranks an exact code, then a code prefix, then a name prefix, once each, at most 20", () => {
    const rows = [hit("3", "Grid Echo Ltd", "GEL"), hit("2", "Alpha", "ECHOX"), hit("1", "Zed", "ECHO"), hit("4", "Echo Partners", "EPX"), hit("2", "Alpha", "ECHOX")];
    expect(rankHits(rows, "echo").map((h) => h.id)).toEqual(["1", "2", "4", "3"]);
    const many = Array.from({ length: 30 }, (_, i) => hit(String(i), `Name ${String(i).padStart(2, "0")}`, `T${i}`));
    expect(rankHits(many, "name")).toHaveLength(20);
  });

  it("'/' jumps to the box except while typing in a field", () => {
    expect(typingIn({ tagName: "INPUT" })).toBe(true);
    expect(typingIn({ tagName: "textarea" })).toBe(true);
    expect(typingIn({ tagName: "SELECT" })).toBe(true);
    expect(typingIn({ tagName: "DIV", isContentEditable: true })).toBe(true);
    expect(typingIn({ tagName: "BODY" })).toBe(false);
    expect(typingIn({ tagName: "A" })).toBe(false);
    expect(typingIn(null)).toBe(false);
  });
});

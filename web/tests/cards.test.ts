import { describe, expect, it } from "vitest";
import { CITE, citeView, factOrder, rehypeCites, stripSection, stripTitle } from "@/lib/cards";
import { repoFile } from "./repo";

// A card as pipeline/thesis/render.py writes it.
const CARD = [
  "# Echo Grid Corp. (ECHO) — 2026-W38",
  "",
  "Grid demand shows up in backlog first.",
  "",
  "## Facts",
  "- Total backlog reached $13.2 billion [f:00000000-0000-4000-8000-0000000000f1].",
  "- Revenue was $1.16 billion [m:revenue:2026-03-31].",
  "",
  "## Why it may be mispriced",
  "- The price implies 5% growth [c:C2] while S1 fired [s:S1] [f:00000000-0000-4000-8000-0000000000f2] [f:00000000-0000-4000-8000-0000000000f1].",
  "",
  "## Kill criteria",
  "| Metric | Condition | Check after | Why |",
  "|---|---|---|---|",
  "| `m:revenue_ttm_yoy` | < 0.05 | 2026-11-20 | Growth thesis fails |",
  "",
  "## Read next",
  "- [10-Q](https://example.com/10q)",
  "",
].join("\n");

describe("thesis cards on the page (lib/cards.ts)", () => {
  it("drops the card's kill-criteria table (the page shows it live) and keeps the rest", () => {
    const out = stripSection(CARD, "Kill criteria");
    expect(out).not.toContain("Kill criteria");
    expect(out).not.toContain("m:revenue_ttm_yoy");
    expect(out).toContain("## Why it may be mispriced");
    expect(out).toContain("## Read next\n- [10-Q](https://example.com/10q)");
    expect(stripSection(CARD, "kill CRITERIA")).toBe(out); // headings match whatever their case
    expect(stripSection(CARD, "Not there")).toBe(CARD);
  });

  it("drops a section down to the next heading of its level, including its subsections", () => {
    const md = "## A\na\n### A.1\nx\n## B\nb\n# Top\nt";
    expect(stripSection(md, "A")).toBe("## B\nb\n# Top\nt");
    expect(stripSection(md, "B")).toBe("## A\na\n### A.1\nx\n# Top\nt");
    expect(stripSection("## Source health\n| a |\n", "Source health")).toBe("");
  });

  it("drops only a leading # title", () => {
    expect(stripTitle(CARD).startsWith("Grid demand shows up in backlog first.")).toBe(true);
    expect(stripTitle("\n# Title\n\nBody")).toBe("Body");
    expect(stripTitle("Body\n# Not a title")).toBe("Body\n# Not a title");
    expect(stripTitle("## A section")).toBe("## A section");
  });

  it("uses the validator's citation pattern", () => {
    expect(repoFile("pipeline/thesis/validate.py")).toContain(`CITE = re.compile(r"${CITE.source}")`);
  });

  it("numbers the cited facts in order of first appearance", () => {
    expect(factOrder(CARD)).toEqual(["f:00000000-0000-4000-8000-0000000000f1", "f:00000000-0000-4000-8000-0000000000f2"]);
    expect(factOrder("no citations")).toEqual([]);
  });

  it("shows each citation as a short label in plain words that links to its evidence on the company page", () => {
    const facts = factOrder(CARD);
    const co = "00000000-0000-4000-8000-0000000000e1";
    expect(citeView("f:00000000-0000-4000-8000-0000000000f2", co, facts)).toEqual({
      label: "fact 2",
      title: "Verified fact 00000000-0000-4000-8000-0000000000f2",
      href: `/company/${co}#fact-00000000-0000-4000-8000-0000000000f2`,
    });
    expect(citeView("f:ffff", co, facts).label).toBe("fact");
    // a metric by the name the kill criteria use, its period end as the screens say dates (PR 6 review design-F1)
    expect(citeView("m:revenue:2026-03-31", co, facts)).toEqual({ label: "Revenue, Mar 31", title: "Metric revenue:2026-03-31", href: `/company/${co}#fundamentals` });
    expect(citeView("m:revenue_ttm_yoy", co, facts).label).toBe("TTM revenue growth");
    expect(citeView("m:signal:S7", co, facts).label).toBe("Insider buying signal strength");
    // signals, red flags and the Gap's parts by the names the Why panel gives their rows; the code in the title
    expect(citeView("s:S1", co, facts)).toEqual({ label: "Order book", title: "S1 Order-book acceleration", href: `/company/${co}#why` });
    expect(citeView("s:S4", co, facts).label).toBe("Earnings quality");
    expect(citeView("s:R3", co, facts)).toMatchObject({ label: "Auditor change, late filing or going-concern language", title: "R3 Auditor change, late filing or going-concern language" });
    expect(citeView("s:S99", co, facts)).toMatchObject({ label: "S99", title: "Signal S99" });
    expect(citeView("c:C2", co, facts)).toMatchObject({ label: "Growth test", href: `/company/${co}#why` });
    expect(citeView("c:C2", null, facts).href).toBeNull();
    expect(citeView("c:C1", co, facts)).toEqual({ label: "Cheap vs its past", title: "C1 Valuation percentile vs its own history", href: `/company/${co}#why` });
    expect(citeView("c:C3", co, facts)).toMatchObject({ label: "Price move", href: `/company/${co}#why` });
    expect(citeView("c:C1", null, facts).href).toBeNull();
    // no code is a chip's label
    for (const id of ["s:S1", "s:S12", "s:R1", "c:C1", "c:C2", "c:C3", "m:revenue_ttm_yoy", "m:signal:S4"]) {
      expect([id, /\b[SRC]\d{1,2}\b/.test(citeView(id, co, facts).label)]).toEqual([id, false]);
    }
  });

  it("splits citations out of text for the chips, and leaves code alone", () => {
    const tree = {
      type: "root",
      children: [
        { type: "element", tagName: "p", children: [{ type: "text", value: "Backlog rose [f:abc] and [m:revenue:2026-03-31]." }] },
        { type: "element", tagName: "code", children: [{ type: "text", value: "[f:x]" }] },
        { type: "element", tagName: "p", children: [{ type: "text", value: "[not a cite] [x:y]" }] },
      ],
    };
    rehypeCites()(tree);
    expect(tree.children[0]).toEqual({
      type: "element",
      tagName: "p",
      children: [
        { type: "text", value: "Backlog rose " },
        { type: "element", tagName: "span", properties: { dataCite: "f:abc" }, children: [{ type: "text", value: "[f:abc]" }] },
        { type: "text", value: " and " },
        { type: "element", tagName: "span", properties: { dataCite: "m:revenue:2026-03-31" }, children: [{ type: "text", value: "[m:revenue:2026-03-31]" }] },
        { type: "text", value: "." },
      ],
    });
    expect(tree.children[1]).toEqual({ type: "element", tagName: "code", children: [{ type: "text", value: "[f:x]" }] });
    expect(tree.children[2]).toEqual({ type: "element", tagName: "p", children: [{ type: "text", value: "[not a cite] [x:y]" }] });
  });
});

describe("citation anchors (integration review web-WEB-1)", () => {
  it("point only at sections the Company page has", () => {
    const page = repoFile("web/app/(app)/company/[id]/page.tsx") + repoFile("web/components/score.tsx");
    const co = "00000000-0000-4000-8000-000000000001";
    for (const id of ["s:S1", "s:R2", "c:C1", "c:C2", "c:C3", "m:revenue"]) {
      const hash = (citeView(id, co, []).href ?? "").split("#")[1];
      expect([id, page.includes(`id="${hash}"`) || page.includes(`["${hash}",`)]).toEqual([id, true]);
    }
  });
});

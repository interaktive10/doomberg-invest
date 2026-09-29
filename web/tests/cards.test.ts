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

  it("shows each citation as a short label that links to its evidence on the company page", () => {
    const facts = factOrder(CARD);
    const co = "00000000-0000-4000-8000-0000000000e1";
    expect(citeView("f:00000000-0000-4000-8000-0000000000f2", co, facts)).toEqual({
      label: "fact 2",
      title: "Verified fact 00000000-0000-4000-8000-0000000000f2",
      href: `/company/${co}#fact-00000000-0000-4000-8000-0000000000f2`,
    });
    expect(citeView("f:ffff", co, facts).label).toBe("fact");
    expect(citeView("m:revenue:2026-03-31", co, facts)).toEqual({ label: "Revenue 2026-03-31", title: "Metric revenue:2026-03-31", href: `/company/${co}#fundamentals` });
    expect(citeView("m:revenue_ttm_yoy", co, facts).label).toBe("Revenue ttm yoy");
    expect(citeView("s:S1", co, facts)).toEqual({ label: "S1", title: "Order-book acceleration", href: `/company/${co}#signals` });
    expect(citeView("s:R3", co, facts).title).toBe("Auditor change, late filing or going-concern language");
    expect(citeView("c:C2", co, facts)).toMatchObject({ label: "C2", href: `/company/${co}#context` });
    expect(citeView("c:C2", null, facts).href).toBeNull();
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

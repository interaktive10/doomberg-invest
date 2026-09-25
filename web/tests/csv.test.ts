import { describe, expect, it } from "vitest";
import { cell, toCsv } from "@/lib/csv";

describe("CSV export", () => {
  it("quotes commas, quotes and line breaks (RFC 4180)", () => {
    expect(cell('Acme, "Inc"')).toBe('"Acme, ""Inc"""');
    expect(cell("a\nb")).toBe('"a\nb"');
    expect(cell(null)).toBe("");
    expect(cell(["S1", "S9"])).toBe("S1 S9");
  });
  it("defuses cells a spreadsheet would run as formulas, but keeps negative numbers", () => {
    expect(cell("=HYPERLINK(\"x\")")).toBe("\"'=HYPERLINK(\"\"x\"\")\"");
    expect(cell("+1+1")).toBe("'+1+1");
    expect(cell("@SUM(A1)")).toBe("'@SUM(A1)");
    expect(cell("-12.5")).toBe("-12.5");
    expect(cell(-3)).toBe("-3");
  });
  it("writes a header and CRLF rows", () => {
    expect(toCsv(["a", "b"], [{ a: 1, b: "x" }])).toBe("a,b\r\n1,x\r\n");
  });
});

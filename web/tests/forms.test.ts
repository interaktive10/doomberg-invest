import { describe, expect, it } from "vitest";
import { field, one, safePath, withMessage } from "@/lib/forms";

describe("server-action helpers", () => {
  it("returns only to a same-site path (no open redirect)", () => {
    expect(safePath("/candidates?bucket=early", "/")).toBe("/candidates?bucket=early");
    expect(safePath("https://evil.example/", "/candidates")).toBe("/candidates");
    expect(safePath("//evil.example/", "/candidates")).toBe("/candidates");
    expect(safePath("/\\evil.example", "/candidates")).toBe("/candidates");
  });
  it("sets one message and keeps the other query parameters", () => {
    expect(withMessage("/candidates?bucket=early&error=old", "ok", "Dismissed.")).toBe("/candidates?bucket=early&ok=Dismissed.");
    expect(withMessage("/theses/1", "error", "A reason is needed")).toBe("/theses/1?error=A+reason+is+needed");
  });
  it("reads trimmed text fields and the first query value", () => {
    const f = new FormData();
    f.set("reason", "  too early  ");
    expect(field(f, "reason")).toBe("too early");
    expect(field(f, "missing")).toBe("");
    expect(one({ a: ["x", "y"], b: "z" }, "a")).toBe("x");
  });
});

import { describe, expect, it } from "vitest";
import { isAllowed, normalizeEmail } from "@/lib/allowlist";

describe("allowlist (BRIEF §6: magic link for APP_ALLOWED_EMAIL only)", () => {
  it("accepts the allowed email, whatever its case or spacing", () => {
    expect(isAllowed("Manzoor@Example.com ", "manzoor@example.com")).toBe(true);
    expect(normalizeEmail("  A@B.co ")).toBe("a@b.co");
  });
  it("refuses any other email, an empty one, and everything when nothing is configured", () => {
    expect(isAllowed("intruder@example.com", "manzoor@example.com")).toBe(false);
    expect(isAllowed("manzoor@example.com.evil.com", "manzoor@example.com")).toBe(false);
    expect(isAllowed("", "manzoor@example.com")).toBe(false);
    expect(isAllowed(null, "manzoor@example.com")).toBe(false);
    expect(isAllowed("manzoor@example.com", "")).toBe(false);
    expect(isAllowed("manzoor@example.com", undefined)).toBe(false);
  });
});

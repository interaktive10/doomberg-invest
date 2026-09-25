import { describe, expect, it } from "vitest";
import { redirectTo } from "@/lib/redirect";

describe("redirects (middleware and auth routes)", () => {
  it("keep the browser on its own host: the Location is relative", () => {
    const r = redirectTo("/login?error=x");
    expect(r.status).toBe(307);
    expect(r.headers.get("location")).toBe("/login?error=x");
    expect(redirectTo("/login", 303).status).toBe(303);
  });
});

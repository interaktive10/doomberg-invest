import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { redirectTo, toLogin } from "@/lib/redirect";

describe("redirects", () => {
  it("auth routes keep the browser on its own host: the Location is relative", () => {
    const r = redirectTo("/login?error=x");
    expect(r.status).toBe(307);
    expect(r.headers.get("location")).toBe("/login?error=x");
    expect(redirectTo("/login", 303).status).toBe(303);
  });

  it("the middleware sends a signed-out visit to /login with an absolute URL on the request's host", () => {
    // CI run on f9370be: a relative Location from the middleware threw "Invalid URL" and the page rendered signed out.
    const r = toLogin(new NextRequest("http://localhost:3000/candidates?bucket=new"));
    expect(r.status).toBe(307);
    const location = new URL(r.headers.get("location") ?? "");
    expect(location.origin).toBe("http://localhost:3000");
    expect(location.pathname).toBe("/login");
    expect(location.search).toBe("");
  });
});

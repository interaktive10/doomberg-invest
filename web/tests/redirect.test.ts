import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { redirectTo, toLogin } from "@/lib/redirect";
import config from "../next.config";

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

  it("the Screener's and the Capex Desk's old links land on Candidates and on This week (overhaul PR 4)", async () => {
    const rules = (await config.redirects?.()) ?? [];
    const to = (path: string) => {
      const r = rules.find((x: { source: string; destination: string; permanent?: boolean }) => new RegExp(`^${x.source.replace("/:path*", "(?:/.*)?")}$`).test(path));
      return r === undefined ? null : [r.destination, r.permanent];
    };
    expect(to("/screener")).toEqual(["/candidates", false]);
    expect(to("/screener/export")).toEqual(["/candidates", false]);
    expect(to("/capex")).toEqual(["/", false]);
    expect(to("/candidates")).toBeNull();
    expect(to("/screenerx")).toBeNull();
  });
});

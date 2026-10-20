import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { repoFile } from "./repo";

// config/guards.yaml (protected) scans web/app, web/components and web/lib. The root files are outside its scan_paths:
// middleware.ts, which runs on every request, and the *.config files. Widening scan_paths needs a human-approved change
// (docs/SPEC_ISSUES.md 33), so this test applies the same banned lists to them meanwhile (M7 review R1-F7).

const WEB = fileURLToPath(new URL("..", import.meta.url));
const GUARDS = repoFile("config/guards.yaml");

/** A flow list of config/guards.yaml (`key: [a, "b", ...]`, over one or more lines). */
function list(key: string): string[] {
  const at = GUARDS.search(new RegExp(`^${key}:`, "m"));
  const open = GUARDS.indexOf("[", at);
  const close = GUARDS.indexOf("]", open);
  return GUARDS.slice(open + 1, close)
    .split(",")
    .map((x) => x.trim().replace(/^["']|["']$/g, ""))
    .filter(Boolean);
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");

/** What the guard's lists find in a file's text. */
export function violations(text: string): string[] {
  const out: string[] = [];
  for (const d of list("banned_runtime_domains")) if (text.includes(d)) out.push(`domain ${d}`);
  for (const id of list("banned_code_identifiers")) if (new RegExp(`\\b${escape(id)}\\b`).test(text)) out.push(`identifier ${id}`);
  for (const pkg of list("banned_npm_packages")) {
    const p = escape(pkg);
    if (new RegExp(`(?:from\\s*|require\\(\\s*|import\\(\\s*)["']${p}(?:/[^"']*)?["']`).test(text)) out.push(`package ${pkg}`);
  }
  return out;
}

const ROOT_FILES = readdirSync(WEB).filter((f) => /\.(?:[cm]?[jt]s)$/.test(f) && !f.endsWith(".d.ts") && statSync(`${WEB}/${f}`).isFile());

describe("guard rules cover the root files (M7 review R1-F7)", () => {
  it("reads the lists from config/guards.yaml and finds what the guard would", () => {
    expect(list("banned_runtime_domains")).toContain("api.kite.trade");
    expect(list("banned_code_identifiers")).toContain("placeOrder");
    expect(list("banned_npm_packages")).toContain("kiteconnect");
    const planted = 'import { KiteConnect } from "kiteconnect";\nkite.placeOrder("regular", {});\nfetch("https://api.kite.trade/orders/regular");\n';
    expect(violations(planted)).toEqual(["domain api.kite.trade", "identifier placeOrder", "package kiteconnect"]);
  });

  it("finds nothing in middleware.ts and the *.config files", () => {
    expect(ROOT_FILES).toContain("middleware.ts");
    expect(ROOT_FILES).toContain("next.config.ts");
    for (const f of ROOT_FILES) expect([f, violations(readFileSync(`${WEB}/${f}`, "utf8"))]).toEqual([f, []]);
  });

  it("package.json depends on no banned npm package", () => {
    const pkg = JSON.parse(readFileSync(`${WEB}/package.json`, "utf8")) as Record<string, Record<string, string> | undefined>;
    const deps = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
    expect(deps.filter((d) => list("banned_npm_packages").includes(d))).toEqual([]);
  });
});

describe("every page checks the session (M7 review R1-F10)", () => {
  function pages(dir: string): string[] {
    return readdirSync(dir).flatMap((f) => {
      const p = `${dir}/${f}`;
      return statSync(p).isDirectory() ? pages(p) : f === "page.tsx" ? [p] : [];
    });
  }
  it("calls requireUser() in every page under app/(app)", () => {
    const all = pages(`${WEB}/app/(app)`);
    expect(all.length).toBeGreaterThanOrEqual(8); // 10 until the Screener and the Capex Desk went (overhaul PR 4)
    expect(all.filter((p) => !readFileSync(p, "utf8").includes("await requireUser()"))).toEqual([]);
  });
});

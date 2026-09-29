import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// BRIEF §8 M7-02: the web app makes no LLM calls at all. e2e/network.spec.ts asserts it on the wire; this test keeps
// LLM endpoints and SDKs out of the source and the dependencies.
const WEB = fileURLToPath(new URL("..", import.meta.url));
const HOSTS = ["generativelanguage.googleapis.com", "api.groq.com", "openrouter.ai", "api.openai.com", "api.anthropic.com"];
const SDKS = /(?:from\s+|require\(|import\()\s*["'](?:openai|groq-sdk|@anthropic-ai\/sdk|@google\/genai|@google\/generative-ai|ai|@ai-sdk\/[\w-]+|langchain|@langchain\/[\w-]+)["']/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    // the app's code only: the tests (tests/, e2e/) name the LLM hosts they assert against
    if (["node_modules", ".next", "tests", "e2e", "test-results", "playwright-report"].includes(name)) return [];
    const p = join(dir, name);
    return statSync(p).isDirectory() ? files(p) : /\.(tsx?|mjs|cjs|js)$/.test(name) ? [p] : [];
  });
}

describe("no LLM in the web app (M7-02)", () => {
  it("no source file names an LLM endpoint or imports an LLM SDK", () => {
    const hits = files(WEB).flatMap((p) => {
      const text = readFileSync(p, "utf8");
      return [...HOSTS.filter((h) => text.includes(h)), ...(SDKS.test(text) ? ["an LLM SDK import"] : [])].map((w) => `${p}: ${w}`);
    });
    expect(hits).toEqual([]);
  });

  it("no dependency is an LLM SDK", () => {
    const pkg = JSON.parse(readFileSync(join(WEB, "package.json"), "utf8")) as Record<string, Record<string, string> | undefined>;
    const deps = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
    expect(deps.filter((d) => /openai|anthropic|genai|generative-ai|groq|langchain|^ai$|@ai-sdk/i.test(d))).toEqual([]);
  });
});

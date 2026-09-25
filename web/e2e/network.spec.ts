import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { PAGES } from "./seed";

// BRIEF §8 M7-02: the web app makes no LLM calls at all. The browser talks only to the app; the server only to the
// Supabase stack (every outbound connection of the Next server is in e2e/.net-log.jsonl, e2e/net-log.cjs).
const LOCAL = new Set(["127.0.0.1", "localhost", "::1"]);
const LLM = ["googleapis.com", "groq.com", "openrouter.ai", "openai.com", "anthropic.com"];

test("no LLM calls, from the browser or the server", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));
  for (const path of PAGES) {
    await page.goto(path);
    await expect(page.locator("main h1").first()).toBeVisible();
  }
  expect((await page.request.get("/screener/export?min_evidence=10")).ok()).toBe(true);

  const hosts = [...new Set(requests.filter((u) => u.startsWith("http")).map((u) => new URL(u).host))];
  expect(hosts).toEqual(["127.0.0.1:3000"]);

  const log = readFileSync("e2e/.net-log.jsonl", "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l) as { host: string; port: number | null });
  expect(log.length).toBeGreaterThan(0); // the hook saw the Supabase calls
  expect(log.filter((c) => !LOCAL.has(c.host))).toEqual([]);
  expect(log.filter((c) => LLM.some((h) => c.host.includes(h)))).toEqual([]);
});

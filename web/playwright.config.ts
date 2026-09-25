import { defineConfig, devices } from "@playwright/test";

// BRIEF §8 M7 on `next start` against the local Supabase stack (CI job `web`): M7-01 the flow (e2e/auth.setup.ts,
// e2e/flow.spec.ts), M7-02 no LLM calls (e2e/network.spec.ts; the server's outbound connections are logged by
// e2e/net-log.cjs), M7-03 axe at 390 px (e2e/a11y.spec.ts).
const env = Object.fromEntries(Object.entries(process.env).filter((e): e is [string, string] => e[1] !== undefined));

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"], ["html", { open: "never" }], ["json", { outputFile: "e2e-report.json" }]],
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "app",
      testMatch: /.*\.spec\.ts/,
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/user.json" },
    },
  ],
  webServer: {
    command: "node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3000",
    url: "http://127.0.0.1:3000/login",
    reuseExistingServer: false,
    timeout: 120_000,
    env: { ...env, NODE_OPTIONS: "--require ./e2e/net-log.cjs", NET_LOG_FILE: "e2e/.net-log.jsonl", NEXT_TELEMETRY_DISABLED: "1" },
  },
});

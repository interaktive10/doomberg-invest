import { defineConfig, devices } from "@playwright/test";

// Screenshots for UI review (`pnpm screens`; .github/workflows/ui-screens.yml): the e2e login, then every screen at a
// desktop and a phone width. Same server and base URL as playwright.config.ts.
const env = Object.fromEntries(Object.entries(process.env).filter((e): e is [string, string] => e[1] !== undefined));

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3000" },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "screens",
      testMatch: /.*\.shot\.ts/,
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/user.json" },
    },
  ],
  webServer: {
    command: "node node_modules/next/dist/bin/next start --port 3000",
    url: "http://localhost:3000/login",
    reuseExistingServer: false,
    timeout: 120_000,
    env: { ...env, NEXT_TELEMETRY_DISABLED: "1" },
  },
});

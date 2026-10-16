import { defineConfig, devices } from "@playwright/test";

/**
 * The E2E runs against the real stack: `web` (nginx + SPA), `api` (FastAPI), `mailpit`,
 * `postgres`, `redis`. Everything communicates over the internal `testnet` network defined in
 * `docker-compose.test.yml`; no outbound traffic is allowed, and no fake LLM is needed for the
 * auth flows (they never hit the agents).
 */

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // one window at a time keeps the shared DB predictable
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    headless: true,
    viewport: { width: 1280, height: 720 },
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

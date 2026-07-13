import * as path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Boots the real stack — no mocks:
 *  - pb-api via uvicorn on :8010 (SQLite database file, migrations applied first)
 *  - @pb/web via `next start` on :3010 (production build; `pretest` builds it)
 *
 * CI sets the CI env var: retries and trace collection tighten accordingly.
 */

const repoRoot = path.resolve(__dirname, "../..");
const apiDir = path.join(repoRoot, "apps/api");
const webDir = path.join(repoRoot, "apps/web");
const dbPath = path.join(__dirname, ".tmp", "e2e.db");

export const API_URL = "http://127.0.0.1:8010";
export const WEB_URL = "http://127.0.0.1:3010";

const apiEnv = {
  PB_API_DATABASE_URL: `sqlite+aiosqlite:///${dbPath}`,
  PB_API_SECRET_KEY: "e2e-suite-jwt-signing-key-with-plenty-of-entropy",
  PB_API_CORS_ORIGINS: `["${WEB_URL}"]`,
  PB_API_LOG_LEVEL: "WARNING",
  PB_ENVIRONMENT: "test",
};

// Sandboxes with a preinstalled Chromium expose it here; on a normal machine
// `playwright install` provides the browser and this stays unset.
const chromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;

export default defineConfig({
  testDir: "./specs",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  timeout: 30_000,
  use: {
    baseURL: WEB_URL,
    trace: "on-first-retry",
    ...(chromiumExecutable ? { launchOptions: { executablePath: chromiumExecutable } } : {}),
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `rm -rf ${path.dirname(dbPath)} && mkdir -p ${path.dirname(dbPath)} && uv run alembic upgrade head && uv run uvicorn pb_api.main:app --host 127.0.0.1 --port 8010`,
      cwd: apiDir,
      url: `${API_URL}/api/v1/health/live`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: apiEnv,
    },
    {
      command: "pnpm exec next start --port 3010",
      cwd: webDir,
      url: WEB_URL,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        PB_WEB_API_INTERNAL_URL: API_URL,
        NEXT_PUBLIC_API_URL: API_URL,
      },
    },
  ],
});

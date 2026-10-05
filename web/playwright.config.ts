import { defineConfig, devices } from "@playwright/test";

// The end-to-end test runs against a compose stack someone else started (CLAUDE.md, Commands): it
// starts nothing itself, so the stack under test is the one users run. E2E_BASE_URL names the
// web client; the default is the stack `docker compose up` serves.
//
// Every run records video. In CI the recording is the onboarding screencast in the README, so the
// run there is paced for a person to follow (E2E_PACE, in milliseconds per screen); locally it is
// not, and the video is only there when something fails.
export default defineConfig({
  testDir: "e2e",
  outputDir: "test-results",
  forbidOnly: !!process.env.CI,
  retries: 0,
  // Signing in, reading the export and importing are each a round trip through the stack; a
  // paced run adds a pause per screen on top.
  timeout: 120_000,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://localhost:8080/app/",
    // The browser trusts the stack's CA the way a person's does: the keychain on macOS, the NSS
    // store on Linux (the CI job adds it there). Nothing here waves a certificate through.
    ignoreHTTPSErrors: false,
    locale: "en-US",
    timezoneId: "America/Los_Angeles",
    viewport: { width: 1280, height: 800 },
    video: { mode: "on", size: { width: 1280, height: 800 } },
    trace: "retain-on-failure",
  },
  // ADR-0049 names Chromium, Firefox and WebKit. One engine runs while there is one test; the
  // others are a project each when the suite grows past the onboarding path.
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
});

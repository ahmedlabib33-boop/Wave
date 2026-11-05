import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  outputDir: process.env.EVIDENCE_ROOT
    ? process.env.EVIDENCE_ROOT + "/browser-artifacts"
    : "test-results",
  timeout: 60000,
  expect: { timeout: 15000 },
  workers: 1,
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile:
          (process.env.EVIDENCE_ROOT || "../research") +
          "/browser-results.json",
      },
    ],
  ],
  use: {
    baseURL: process.env.UI_URL || "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    { name: "iphone-webkit", use: { ...devices["iPhone 15 Pro Max"] } },
  ],
});

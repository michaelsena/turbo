import { defineConfig } from "@playwright/test";

const externalBaseURL = process.env.TURBO_TEST_BASE_URL;
if (externalBaseURL) {
  const url = new URL(externalBaseURL);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(url.hostname)
    || url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("TURBO_TEST_BASE_URL must be an HTTP loopback origin (127.0.0.1 or localhost).");
  }
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "list",
  outputDir: "test-results",
  snapshotPathTemplate: "{testDir}/__screenshots__/{projectName}/{arg}{ext}",
  use: {
    baseURL: externalBaseURL ?? "http://127.0.0.1:8017",
    channel: "chrome",
    colorScheme: "light",
    locale: "en-US",
    reducedMotion: "reduce",
    timezoneId: "UTC",
    trace: "off",
  },
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.005,
    },
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    {
      name: "mobile",
      use: {
        browserName: "chromium",
        channel: "chrome",
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 1,
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
  webServer: externalBaseURL ? undefined : {
    command: "PYTHONPATH=src .venv/bin/python -m uvicorn turbo.web.app:app --host 127.0.0.1 --port 8017",
    cwd: "..",
    url: "http://127.0.0.1:8017/api/v1/context",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});

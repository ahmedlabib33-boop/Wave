import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const token = process.env.TEST_API_TOKEN || readFileSync("../data/access-token", "utf8").trim();

async function login(page) {
  await page.goto("/");
  await page.getByLabel("Server access token").fill(token);
  await page.getByRole("button", { name: "Connect to hub", exact: true }).click();
  await expect(page.getByText("Backend connected", { exact: true })).toBeVisible();
}

test("street viewer selects real cached street metadata without inventing coverage", async ({ page, isMobile }) => {
  await login(page);
  if (isMobile)
    await page.getByRole("button", { name: "Monitoring workspace", exact: true }).click();
  await page.locator(".sidebar nav").getByRole("button", { name: "Greater Cairo Street Viewer", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Greater Cairo Street Viewer", exact: true })).toBeVisible();
  await expect(page.getByTestId("street-map").locator("canvas")).toBeVisible();
  await page.getByRole("button", { name: "Browser fixture street", exact: true }).click();
  await expect(page.getByText("Selected street", { exact: true })).toBeVisible();
  await expect(page.getByText("No recent browser playback evidence", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

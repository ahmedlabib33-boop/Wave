import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const token =
  process.env.TEST_API_TOKEN ||
  readFileSync("../data/access-token", "utf8").trim();
async function login(page) {
  await page.goto("/");
  await page.getByLabel("Server access token").fill(token);
  await page
    .getByRole("button", { name: "Connect to hub", exact: true })
    .click();
  await expect(
    page.getByText("Backend connected", { exact: true }),
  ).toBeVisible();
}
async function navigate(page, name, mobile) {
  if (mobile)
    await page
      .getByRole("button", { name: "Monitoring workspace", exact: true })
      .click();
  await page
    .locator(".sidebar nav")
    .getByRole("button", { name, exact: true })
    .click();
}

test("regional scope preserves radar and metadata cannot become a feed without permission", async ({
  page,
  isMobile,
}, testInfo) => {
  await login(page);
  await navigate(page, "Live Cameras", isMobile);
  const region = page.locator(".regional-discovery");
  await region.locator("summary").first().click();
  await expect(
    region.getByLabel("South latitude", { exact: true }),
  ).toBeVisible();
  await region.getByLabel("South latitude", { exact: true }).fill("29.8");
  await region
    .getByRole("button", { name: "Save investigation area", exact: true })
    .click();
  await expect
    .poll(async () => {
      const r = await page.request.get("/api/discovery/area", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return (await r.json()).south;
    })
    .toBe(29.8);
  const settings = await page.request.get("/api/settings", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect((await settings.json()).radius_m).toBe(5000);
  await region.locator(".manual-candidate summary").click();
  const name = `UI-only permission fixture · ${testInfo.project.name} · ${Date.now()}`;
  await region
    .locator(".manual-candidate")
    .getByLabel("Name", { exact: true })
    .fill(name);
  await region
    .getByRole("button", { name: "Record candidate", exact: true })
    .click();
  const card = region
    .locator(".candidate-card")
    .filter({ has: page.getByRole("heading", { name, exact: true }) });
  await expect(card).toBeVisible();
  await expect(
    card.getByRole("button", { name: "Check authorized stream", exact: true }),
  ).toHaveCount(0);
  await expect(
    card.getByRole("button", {
      name: "Add verified stream to hub",
      exact: true,
    }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("regional camera investigation supports Arabic RTL", async ({
  page,
  isMobile,
}, testInfo) => {
  await login(page);
  await navigate(page, "Settings", isMobile);
  await page
    .getByRole("button", { name: "العربية", exact: true })
    .last()
    .click();
  if (isMobile)
    await page
      .getByRole("button", { name: "مساحة المراقبة", exact: true })
      .click();
  await page
    .locator(".sidebar nav")
    .getByRole("button", { name: "الكاميرات المباشرة", exact: true })
    .click();
  const region = page.locator(".regional-discovery");
  await region.locator("summary").first().click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(
    region.getByLabel("خط العرض الجنوبي", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: `${process.env.EVIDENCE_ROOT || "../research/continuation/regression"}/screenshots/${testInfo.project.name}-discovery-arabic.png`,
    fullPage: true,
  });
});

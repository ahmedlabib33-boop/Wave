import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const token =
  process.env.TEST_API_TOKEN ||
  readFileSync("../data/access-token", "utf8").trim();
const evidenceRoot = process.env.EVIDENCE_ROOT || "../research";
const names = [
  "Radar Overview",
  "Live Cameras",
  "Traffic Speeds",
  "Aircraft",
  "Marine",
  "Satellite Radar",
  "Sensor Hub",
  "Historical Observations",
  "Source Diagnostics",
  "Settings",
];
const arabic = [
  "نظرة الرادار",
  "الكاميرات المباشرة",
  "سرعات المرور",
  "الطائرات",
  "الملاحة البحرية",
  "الرادار الفضائي",
  "مركز المستشعرات",
  "سجل الرصد",
  "تشخيص المصادر",
  "الإعدادات",
];
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

test("real workspace and geographic map render without invented objects", async ({
  page,
  isMobile,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await expect(page.locator("h1")).toHaveText("A clear view of what is known.");
  await expect(page.getByTestId("radar-map").locator("canvas")).toBeVisible();
  await expect(
    page.getByRole("slider", { name: "Radius", exact: true }),
  ).toHaveValue("5000");
  const bounds = await page.getByTestId("radar-map").boundingBox();
  expect(bounds!.width).toBeGreaterThan(250);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await expect(page.getByTestId("radar-map")).toHaveAttribute(
    "data-map-ready",
    "true",
  );
  await page.screenshot({
    path: `${evidenceRoot}/screenshots/${testInfo.project.name}-radar.png`,
    fullPage: true,
  });
  expect(errors).toEqual([]);
  await navigate(page, "Source Diagnostics", isMobile);
  await expect(
    page.getByRole("heading", {
      name: "Egypt enforcement cameras",
      exact: true,
    }),
  ).toBeVisible();
});

test("all ten pages and complete RTL layout", async ({
  page,
  isMobile,
}, testInfo) => {
  await login(page);
  for (const name of names) {
    await navigate(page, name, isMobile);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
  await page
    .getByRole("button", { name: "العربية", exact: true })
    .last()
    .click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  for (const name of arabic) {
    if (isMobile)
      await page
        .getByRole("button", { name: "مساحة المراقبة", exact: true })
        .click();
    await page
      .locator(".sidebar nav")
      .getByRole("button", { name, exact: true })
      .click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
  if (isMobile)
    await page
      .getByRole("button", { name: "مساحة المراقبة", exact: true })
      .click();
  await page
    .locator(".sidebar nav")
    .getByRole("button", { name: arabic[0], exact: true })
    .click();
  await expect(page.locator("h1")).toHaveText("رؤية واضحة لما نعرفه.");
  await expect(page.getByTestId("radar-map")).toHaveAttribute(
    "data-map-ready",
    "true",
  );
  await page.screenshot({
    path: `${evidenceRoot}/screenshots/${testInfo.project.name}-arabic.png`,
    fullPage: true,
  });
});

test("radius settings persist from 1 to 5 km", async ({ page }) => {
  await login(page);
  const slider = page.getByRole("slider", { name: "Radius", exact: true });
  await slider.focus();
  await slider.press("Home");
  await expect(slider).toHaveValue("1000");
  await expect
    .poll(async () => {
      const r = await page.request.get("/api/settings", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return (await r.json()).radius_m;
    })
    .toBe(1000);
  await slider.press("End");
  await expect(slider).toHaveValue("5000");
  await expect
    .poll(async () => {
      const r = await page.request.get("/api/settings", {
        headers: { Authorization: `Bearer ${token}` },
      });
      return (await r.json()).radius_m;
    })
    .toBe(5000);
});

test("historical satellite metadata is browsable and labelled", async ({
  page,
  isMobile,
}) => {
  await login(page);
  await navigate(page, "Satellite Radar", isMobile);
  await expect(
    page.getByText("Historical SAR acquisitions and scene footprints.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.locator(".scene-row").first()).toBeVisible();
  await page.locator(".scene-row").first().click();
  await expect(page.locator(".scene-detail")).toBeVisible();
  await expect(
    page.locator(".scene-detail").getByText("Acquisition", { exact: true }),
  ).toBeVisible();
});

test("bad access token is rejected", async ({ page }) => {
  await page.goto("/");
  await page
    .getByLabel("Server access token")
    .fill("incorrect-access-token-over-24-characters");
  await page
    .getByRole("button", { name: "Connect to hub", exact: true })
    .click();
  await expect(page.getByRole("alert")).toHaveText(
    "Connection failed. Check the server and access token.",
  );
  await expect(page.locator(".sidebar")).toHaveCount(0);
});

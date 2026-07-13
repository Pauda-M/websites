import { expect, test } from "@playwright/test";

test.describe("landing page", () => {
  test("renders the PB Solutions brand and hero", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/PB Solutions/);
    await expect(page.getByRole("banner").getByText("PB Solutions")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("shows the four service offerings", async ({ page }) => {
    await page.goto("/");
    for (const service of [
      "Consulting",
      "CRM & Client Portal",
      "AI Services",
      "Support & Ticketing",
    ]) {
      await expect(page.getByRole("heading", { name: service, exact: true })).toBeVisible();
    }
  });

  test("navigates to the status page", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Status" }).first().click();
    await expect(page).toHaveURL(/\/status$/);
    await expect(page.getByRole("heading", { name: /platform status/i })).toBeVisible();
  });
});

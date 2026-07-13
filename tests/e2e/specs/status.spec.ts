import { expect, test } from "@playwright/test";

test.describe("status page (web -> api integration)", () => {
  test("reports the API as operational", async ({ page }) => {
    await page.goto("/status");

    // The web server fetched both health endpoints server-side via @pb/api-client.
    await expect(page.getByRole("heading", { name: /platform status/i })).toBeVisible();
    await expect(page.getByText("API unreachable")).toHaveCount(0);
    await expect(page.getByText("Operational").first()).toBeVisible();
  });

  test("shows liveness details from the API", async ({ page }) => {
    await page.goto("/status");
    await expect(page.getByText("pb-api")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Liveness" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Readiness" })).toBeVisible();
  });

  test("lists per-dependency readiness checks", async ({ page }) => {
    await page.goto("/status");
    await expect(page.getByText("database")).toBeVisible();
    await expect(page.getByText("redis")).toBeVisible();
  });
});

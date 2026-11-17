import { expect, test } from "@playwright/test";

import { mockSignedOut } from "./fixtures";

test.describe("navigation & layout", () => {
  test("home renders and the navbar turns to glass on scroll", async ({ page, isMobile }) => {
    await mockSignedOut(page);
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Theatre Mania home" })).toBeVisible();

    if (!isMobile) {
      const bar = page.locator("header > div").first();
      await expect(bar).not.toHaveClass(/glass/);
      await page.mouse.wheel(0, 600);
      await expect(bar).toHaveClass(/glass/);
    } else {
      await expect(page.getByRole("navigation", { name: "Mobile" })).toBeVisible();
    }
  });

  test("protected routes redirect signed-out visitors to login", async ({ page }) => {
    await mockSignedOut(page);
    await page.goto("/my-list");
    await expect(page).toHaveURL(/\/login\?next=%2Fmy-list/);
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  test("unknown routes show the 404 page", async ({ page }) => {
    await mockSignedOut(page);
    await page.goto("/definitely-not-a-page");
    await expect(page.getByText("This reel is missing.")).toBeVisible();
  });

  test("respects prefers-reduced-motion (no custom cursor)", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await mockSignedOut(page);
    await page.goto("/");
    await expect(page.locator("html")).not.toHaveClass(/has-cursor/);
    await context.close();
  });
});

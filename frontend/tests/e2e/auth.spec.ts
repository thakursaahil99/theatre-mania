import { expect, test } from "@playwright/test";

/**
 * Full-stack flows: these talk to the real backend through the Next.js proxy.
 * Run against `docker compose up` (E2E_BASE_URL=http://localhost:3000).
 */
test.describe("auth (full stack)", () => {
  test.skip(!process.env.E2E_FULL_STACK, "set E2E_FULL_STACK=1 with the backend running");

  test("sign up, manage profiles, sign out", async ({ page }) => {
    const email = `e2e-${Date.now()}@example.com`;
    await page.goto("/signup");
    await page.getByLabel("Name").fill("Playwright");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("popcorn-42");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL("/");

    await page.goto("/profiles?manage=1");
    await page.getByRole("button", { name: "Add profile" }).click();
    await page.getByLabel("Profile name").fill("Kids");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("button", { name: "Edit Kids" })).toBeVisible();

    await page.getByRole("button", { name: "Done" }).click();
    await page.getByRole("button", { name: "Watch as Kids" }).click();
    await expect(page).toHaveURL("/");
  });

  test("wrong password shows an error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("nobody@example.com");
    await page.getByLabel("Password", { exact: true }).fill("wrong-password-1");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.locator("form [role=alert]")).toHaveText(/Incorrect email or password/);
  });
});

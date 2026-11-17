import { expect, test } from "@playwright/test";

import { mockSignedOut, movie } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockSignedOut(page);
  await page.route("**/api/v1/movies/genres", (r) => r.fulfill({ json: [{ id: 27, name: "Horror" }, { id: 35, name: "Comedy" }] }));
  await page.route("**/api/v1/search**", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const all = [
      movie(10331, "Night of the Living Dead", { streamable: true }),
      movie(3085, "His Girl Friday", { genre_ids: [35] }),
      movie(19, "Metropolis"),
    ];
    let results = q ? all.filter((m) => m.title.toLowerCase().includes(q)) : all;
    if (url.searchParams.get("free_only") === "true") results = results.filter((m) => m.streamable);
    return route.fulfill({ json: { page: 1, total_pages: 1, total_results: results.length, results } });
  });
});

test("instant search debounces, updates the URL and animates results", async ({ page }) => {
  await page.goto("/search");
  await expect(page.getByRole("link", { name: "Metropolis" })).toBeVisible();

  const searches: string[] = [];
  page.on("request", (req) => req.url().includes("/api/v1/search") && searches.push(req.url()));
  await page.getByLabel("Search films").pressSequentially("night", { delay: 40 });

  await expect(page.getByRole("heading", { name: /Results for “night”/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Night of the Living Dead" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Metropolis" })).toHaveCount(0);
  await expect(page).toHaveURL(/q=night/);
  expect(searches.length).toBeLessThanOrEqual(2); // debounced, not one request per keystroke
});

test("free-to-watch filter", async ({ page }) => {
  await page.goto("/search");
  await page.getByRole("button", { name: "Filters" }).click();
  await page.getByLabel("Free to watch only").check();
  await expect(page.getByRole("link", { name: "Night of the Living Dead" })).toBeVisible();
  await expect(page.getByRole("link", { name: "His Girl Friday" })).toHaveCount(0);
  await expect(page).toHaveURL(/free_only=true/);
});

test("empty state", async ({ page }) => {
  await page.goto("/search?q=zzzz");
  await expect(page.getByText("Nothing matched that search.")).toBeVisible();
});

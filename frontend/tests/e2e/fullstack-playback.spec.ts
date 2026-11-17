import { expect, test } from "@playwright/test";

/**
 * Real playback through the whole stack: Next.js proxy → FastAPI playback token →
 * tokenised playlists → signed segments from object storage → hls.js → <video>.
 * Needs a seeded, transcoded, published title:
 *   docker compose -f infra/docker-compose.yml exec backend python -m scripts.seed_public_domain --only "trip to the moon" --publish
 */
test.describe("full-stack playback", () => {
  test.skip(!process.env.E2E_FULL_STACK, "set E2E_FULL_STACK=1 with the stack running and a title seeded");

  test("a free title streams, resumes and records progress", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    const email = `viewer-${Date.now()}@example.com`;
    await page.goto("/signup");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("popcorn-42");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL("/");

    // Free to Watch row → first title
    await page.goto("/browse/free");
    const first = page.locator("main a[href^='/movie/']").first();
    const href = await first.getAttribute("href");
    expect(href).toMatch(/^\/movie\//);
    await page.goto(href!);
    await page.getByRole("link", { name: /Watch Now|Resume/ }).click();
    await expect(page).toHaveURL(/\/watch\//);

    const video = page.locator("video");
    await expect(video).toBeAttached();
    // Headless autoplay policy varies; start (muted) playback directly rather than racing
    // the Play/Pause button while the stream is still loading.
    await video.evaluate((v: HTMLVideoElement) => {
      v.muted = true;
      return v.play().catch(() => undefined);
    });

    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime), { timeout: 30_000 }).toBeGreaterThan(3);
    const quality = await page.evaluate(() => document.querySelector("video")?.videoHeight ?? 0);
    expect(quality).toBeGreaterThan(0); // real decoded frames, not just a timer

    // Seek forward, leave, and check Continue Watching picked it up.
    await page.keyboard.press("6"); // jump to 60%
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime), { timeout: 15_000 }).toBeGreaterThan(60);
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Continue Watching/ })).toBeVisible({ timeout: 15_000 });
  });
});

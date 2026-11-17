import { expect, test } from "@playwright/test";

import { mockSignedIn, movie } from "./fixtures";

// Public HLS test stream (Mux). Swap for a local fixture if your CI has no internet access.
const TEST_STREAM = process.env.E2E_HLS_URL ?? "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8";

test.describe("player", () => {
  test("unlicensed titles never reach the player", async ({ page }) => {
    await mockSignedIn(page);
    await page.route("**/api/v1/playback/*/start**", (r) =>
      r.fulfill({ status: 403, json: { detail: "This title is not available to stream" } }));
    await page.goto("/watch/550");
    await expect(page.getByRole("heading", { name: "Not available to stream" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Back to details" })).toHaveAttribute("href", "/movie/550");
  });

  test("streams HLS with custom controls, shortcuts and skip intro", async ({ page, isMobile }) => {
    test.skip(isMobile, "keyboard shortcuts are desktop-only");
    await mockSignedIn(page);
    await page.route("**/api/v1/playback/*/start**", (r) =>
      r.fulfill({
        json: {
          session_id: "s1",
          asset_id: "a1",
          movie: movie(10331, "Night of the Living Dead", { streamable: true }),
          master_url: TEST_STREAM, stream_type: "hls",
          duration_seconds: 600,
          resume_position_sec: 0,
          intro_start_sec: 0,
          intro_end_sec: 30,
          credits_start_sec: null,
          subtitles: [],
          token_expires_in: 14400,
        },
      }));

    await page.goto("/watch/10331");
    const player = page.getByTestId("player");
    await expect(player).toBeVisible();
    await expect(page.getByRole("heading", { name: "Night of the Living Dead" })).toBeVisible();

    // Quality menu is populated from the HLS manifest's renditions.
    await page.getByRole("button", { name: "Quality" }).click({ timeout: 20_000 });
    await expect(page.getByRole("menuitemradio", { name: /Auto/ })).toBeVisible();
    await page.keyboard.press("Escape");

    await page.keyboard.press("m");
    await expect(page.getByRole("status")).toHaveText(/Muted/);

    await page.getByRole("button", { name: "Skip Intro" }).click();
    await expect(page.getByRole("button", { name: "Skip Intro" })).toBeHidden();

    await page.keyboard.press(">");
    await expect(page.getByRole("status")).toHaveText(/1.25× speed/);
  });

  test("leaving the player still records progress (final heartbeat)", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await mockSignedIn(page);
    const beats: { position_sec: number; duration_sec: number | null }[] = [];
    await page.route("**/api/v1/playback/sessions/s1/heartbeat", async (r) => {
      beats.push(r.request().postDataJSON());
      await r.fulfill({ status: 204 });
    });
    await page.route("**/api/v1/playback/*/start**", (r) =>
      r.fulfill({
        json: {
          session_id: "s1", asset_id: "a1", movie: movie(10331, "Night of the Living Dead", { streamable: true }),
          master_url: TEST_STREAM, stream_type: "hls", duration_seconds: 600, resume_position_sec: 0, intro_start_sec: null,
          intro_end_sec: null, credits_start_sec: null, subtitles: [], token_expires_in: 14400,
        },
      }));
    // sendBeacon (used for the exit heartbeat) can't be intercepted by page.route, but it is
    // still observable as a network request.
    const observed: { position_sec: number; duration_sec: number | null }[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/playback/sessions/s1/heartbeat") && req.method() === "POST") {
        const body = req.postData();
        if (body) observed.push(JSON.parse(body));
      }
    });

    await page.goto("/watch/10331");
    const video = page.locator("video");
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.duration || 0), { timeout: 30_000 }).toBeGreaterThan(30);
    await page.keyboard.press("5"); // seek to 50%
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime), { timeout: 15_000 }).toBeGreaterThan(20);

    // Leave well inside the 15s heartbeat interval (client-side nav → player unmounts):
    // the exit beacon must still carry the real position. This regressed once because
    // React detaches refs before effect cleanups run.
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await expect(page).toHaveURL(/\/movie\/10331/);
    await expect.poll(() => observed.length + beats.length, { timeout: 10_000 }).toBeGreaterThan(0);
    const all = [...observed, ...beats];
    expect(Math.max(...all.map((b) => b.position_sec))).toBeGreaterThan(20);
    expect(all.at(-1)!.duration_sec).toBeGreaterThan(30);
  });
});

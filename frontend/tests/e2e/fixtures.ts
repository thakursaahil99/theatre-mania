import type { Page } from "@playwright/test";

export const movie = (id: number, title: string, extra: Record<string, unknown> = {}) => ({
  id: String(id),
  tmdb_id: id,
  title,
  overview: `${title} overview`,
  poster_path: null,
  backdrop_path: null,
  release_date: "1968-10-01",
  vote_average: 7.6,
  genre_ids: [27],
  original_language: "en",
  streamable: false,
  ...extra,
});

/** Browser-side API mocks (client components only; server components hit the real API). */
export async function mockSignedOut(page: Page) {
  await page.route("**/api/v1/auth/me", (r) => r.fulfill({ status: 401, json: { detail: "Not authenticated" } }));
  await page.route("**/api/v1/auth/refresh", (r) => r.fulfill({ status: 401, json: { detail: "No refresh token" } }));
}

export async function mockSignedIn(page: Page, { admin = false } = {}) {
  // Marker cookie the route-guard middleware looks for (the real one is set by the backend).
  await page.context().addCookies([{ name: "cv_session", value: "1", url: process.env.E2E_BASE_URL ?? "http://localhost:3000" }]);
  await page.route("**/api/v1/auth/me", (r) =>
    r.fulfill({
      json: {
        user: { id: "u1", email: "viewer@example.com", display_name: "Viewer", is_admin: admin, created_at: "2026-01-01T00:00:00Z" },
        active_profile_id: "p1",
      },
    }),
  );
  await page.route("**/api/v1/profiles", (r) => r.fulfill({ json: [{ id: "p1", name: "Viewer", avatar: "nebula", is_kids: false }] }));
  await page.route("**/api/v1/me/continue-watching", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/v1/playback/sessions/**", (r) => r.fulfill({ status: 204 }));
}

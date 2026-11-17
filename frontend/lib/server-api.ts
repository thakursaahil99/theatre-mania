// Server components only (reads API_INTERNAL_URL, which is never exposed to the browser).
const BASE = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

/**
 * Cache lifetimes for the Next.js data cache. The backend already caches the expensive part
 * (TMDB responses for 24h in Redis), so anything that carries *availability* (whether a title
 * can be streamed right now) is kept short here: a newly published film must show up quickly,
 * and an expired license must disappear quickly.
 */
export const REVALIDATE = {
  library: 0, // Free to Watch list: always fresh (cheap DB query)
  availability: 30, // home rows + detail pages: include `streamable` flags
  catalog: 600, // pure TMDB lists (trending, top rated…)
  static: 86_400, // genre names
} as const;

/**
 * Server-side fetch for public catalog data. Returns null on 404 or when the API is
 * unreachable so pages can render graceful fallbacks instead of crashing.
 * `revalidate: 0` bypasses the data cache entirely.
 */
export async function serverFetch<T>(path: string, revalidate: number = REVALIDATE.availability): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}/api/v1${path}`, {
      ...(revalidate === 0 ? { cache: "no-store" as const } : { next: { revalidate } }),
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

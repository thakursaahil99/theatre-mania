# Theatre Mania

A production-grade streaming platform with a cinematic, highly animated UI, built to stream **only content we have the rights to** (public-domain films, Internet Archive free content, our own and licensed uploads). Every other movie shows TMDB metadata, official trailers and legal "Where to Watch" providers. No third-party ads.

```
backend/    FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL · Redis · Celery · FFmpeg → HLS
frontend/   Next.js 15 (App Router) · TypeScript · Tailwind v4 · Framer Motion · GSAP · Lenis · hls.js
infra/      docker-compose (production-like stack) · nginx edge (signed-segment CDN + cache)
scripts/    npm run setup · dev · seed: native development without Docker
```

---

## Quick start (no Docker, recommended)

Needs only **Node 20+** and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**. Nothing is installed system-wide: Python lives in `backend/.venv`, and on Windows a checksum-verified portable FFmpeg is downloaded into `backend/.tools` (macOS/Linux: `brew install ffmpeg` / `apt install ffmpeg`).

```bash
npm run setup                                         # venv, FFmpeg, backend/.env, DB migrations, frontend deps
npm run dev                                           # API + worker + scheduler + web app, one terminal
npm run seed -- --only "trip to the moon" --publish   # import a free film (about a minute)
```

`npm run dev` picks free ports automatically (preferring web **3000** and API **8000**), wires the URLs between the processes, and prints where the app is running. Ctrl+C stops everything. Add `TMDB_READ_TOKEN` to `backend/.env` for posters, cast, trailers and the TMDB rows.

Native mode swaps the infrastructure for zero-dependency local equivalents, with the same code paths and security model:

| Production | Native dev | Notes |
|---|---|---|
| PostgreSQL | SQLite file (`backend/data/cineverse.db`, WAL mode) | Or set `DATABASE_URL` to your own Postgres |
| Redis (cache, rate limits) | In-process store (`REDIS_URL=memory://`) | |
| Redis (Celery broker) | Kombu filesystem broker (`backend/data/celery`) | Worker runs `--pool=solo` (Windows-compatible) |
| Cloudflare R2 + CDN | Local files (`backend/data/media`) behind `/api/v1/media` | HMAC-signed, expiring URLs; unsigned, tampered or expired requests get 403 |

Other commands: `npm run seed -- --dry-run` (preview all 20 matches), `npm run test` (backend tests + typecheck), `npm run test:e2e`.

1. **Sign up** with an email from `ADMIN_EMAILS` (default `admin@example.com`) to become an admin.
2. **Seed the library** with 20 public-domain films (Internet Archive → TMDB metadata → HLS):
   ```bash
   npm run seed -- --dry-run     # preview matches
   npm run seed                  # import all 20 as drafts
   ```
   Titles are imported and transcoded as **drafts**. Review each print in **Admin → Library** (silent films in particular can carry newer copyrighted scores or re-release edits), then click **Publish**. For a local demo, `--publish` skips the review, and `--only "metropolis,detour"` limits the run to specific titles.

   Internet Archive matching is strict: curated collections first, normalised title similarity, release year within ±2, the upload closest to the original runtime, and no trailers, fragments, multi-part uploads or release-group rips of commercial restorations.

3. **Bulk-import thousands of public-domain films** (streamed directly from archive.org, so no download and no transcode):
   ```bash
   npm run import:archive -- --dry-run --limit 50   # preview
   npm run import:archive                            # up to 4000 films (--limit to change)
   ```
   Only feature-length, single-part uploads from Internet Archive's curated `feature_films` / `silent_films` collections are imported, with the same rip, trailer and fragment filters and one entry per film (the most-viewed upload wins). Rights rules:
   - `--rule date`: dated **1930 or earlier**, so public domain in the US by date; **published** automatically.
   - `--rule asserted`: uploader-declared Public Domain Mark / CC0 / CC BY / CC BY-SA, dated 1977 or earlier. Imported as **drafts**, because the uploader's claim isn't verification. Review them in Admin → Library; `--publish-asserted` skips the review (local demos only).

   Curated and uploaded titles (HLS, our CDN) always sort ahead of bulk imports in Free to Watch.

> **TMDB key:** create one at themoviedb.org → Settings → API. Use the *API Read Access Token* as `TMDB_READ_TOKEN`. Without it the app still runs, but only library rows and fallback metadata are shown.

### Alternative: Docker Compose (production-like)

Runs the real production services (Postgres, Redis, S3-compatible storage, nginx edge):

```bash
cp backend/.env.example backend/.env        # add TMDB_READ_TOKEN, set ADMIN_EMAILS
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec backend python -m scripts.seed_public_domain --dry-run
```

The compose file is self-contained (code and config are baked into images), so it needs no Docker Desktop file-sharing permission. For hot reload, add `-f infra/docker-compose.dev.yml`, which bind-mounts the source (the drive must be shared in Docker Desktop).

| URL | What |
|---|---|
| http://localhost:3000 | App (Next.js; proxies `/api/v1/*` to the API) |
| http://localhost:8000/api/v1/docs | OpenAPI docs (Swagger) |
| http://localhost:8080 | nginx edge (app + `/media` signed-segment CDN) |
| http://localhost:9000 | S3 API (SeaweedFS; key `minioadmin`, secret `minioadmin`) |

**Port clashes?** Copy `infra/.env.example` to `infra/.env` and change `FRONTEND_PORT`, `API_PORT`, `POSTGRES_PORT` and so on. If you move the frontend port, also update `FRONTEND_URL`, `CORS_ORIGINS` and `GOOGLE_REDIRECT_URI` in `backend/.env`.

> Compose's object storage is [SeaweedFS](https://github.com/seaweedfs/seaweedfs) (S3-compatible, Apache-2.0), with credentials in `infra/seaweedfs/s3.json`. MinIO's free container images are no longer published, so it was replaced. Anonymous reads are denied, so presigned URLs are genuinely enforced.

---

## Architecture

```
Browser ──► Next.js (Vercel)  ──/api/v1/* rewrite──►  FastAPI (Railway/Render/VPS)
   │            │ server components fetch catalog         │  ├─ Postgres (users, library, licenses, activity)
   │            ▼                                         │  ├─ Redis (TMDB cache 24h, home cache, rate limits, Celery broker)
   │        hls.js player                                 │  └─ Celery worker: download → ffprobe → FFmpeg ABR → upload
   │            │ master/variant .m3u8 (tokenised, via API)
   │            ▼
   └────► R2 / SeaweedFS / CDN  ◄── signed, expiring segment URLs (anti-hotlinking)
```

**Why the API is proxied through Next.js.** Auth cookies (`httpOnly`, `SameSite=Lax`) stay first-party on the frontend origin, so there is no third-party cookie or `SameSite=None` dance between Vercel and the API host.

**Streaming security**
1. `POST /playback/{id}/start` checks the title is *published*, has an *active license window* and a *ready asset*, then issues a short-lived playback JWT bound to the asset.
2. `GET /stream/{asset}/master.m3u8?token=` rewrites variant URIs back to the API.
3. `GET /stream/{asset}/v/{rendition}.m3u8?token=` rewrites every segment URI into a **signed, expiring URL**, either an S3/R2 presigned GET (`STREAM_SIGNING_MODE=s3`) or a CDN URL validated by nginx `secure_link_md5` (`STREAM_SIGNING_MODE=cdn`, see `infra/nginx`). Without a token nobody can obtain segment URLs, and harvested URLs expire.
4. On a 403 mid-playback the player renews the token in place (`?session_id=`), so renewal never counts as a new view.

**Licensing is enforced in three places:** the SQL `streamable_filter` (used by every row, search, detail and playback check), the admin publish guard, and a Celery Beat job that unpublishes titles whose license expired (every 15 min).

---

## Database schema

| Table | Key columns | Notes |
|---|---|---|
| `users` | `id uuid`, `email` (unique), `password_hash` (argon2, nullable for Google-only), `google_sub` (unique), `is_admin`, `is_active` | |
| `refresh_tokens` | `id` (= JWT `jti`), `user_id`, `family_id`, `expires_at`, `revoked_at` | Rotation on every refresh; replaying a rotated token revokes the whole family |
| `profiles` | `id`, `user_id`, `name`, `avatar`, `is_kids` | Max 4 per account; unique `(user_id, name)` |
| `movies` | `id`, `tmdb_id` (unique, nullable), `slug` (unique), metadata columns, `credits jsonb`, `in_library`, `status` (draft/published/archived), `published_at` | `in_library=false` rows are TMDB stubs created on demand so watchlists and ratings can reference any film |
| `genres` / `movie_genres` | TMDB genre ids | |
| `licenses` | `movie_id`, `license_type` (public_domain / creative_commons / owned / licensed), `licensor`, `source_url`, `territories jsonb`, `starts_at`, `expires_at`, `notes` | Append-only windows (audit trail); latest active one wins |
| `video_assets` | `movie_id`, `status` (pending_upload → queued → downloading → processing → ready / failed), `source_key` / `source_url`, `storage_prefix`, `master_key`, `renditions jsonb`, `duration_seconds`, `intro_start_sec`, `intro_end_sec`, `credits_start_sec`, `progress`, `error` | |
| `subtitles` | `asset_id`, `language`, `label`, `storage_key`, `is_default` | `.srt` uploads are converted to WebVTT |
| `watchlist_items` | PK `(profile_id, movie_id)`, `added_at` | |
| `watch_progress` | PK `(profile_id, movie_id)`, `position_sec`, `duration_sec`, `completed`, `updated_at` | Continue Watching + History |
| `watch_sessions` | `id`, `profile_id`, `movie_id`, `asset_id`, `started_at`, `seconds_watched`, `max_position_sec`, `completed` | Admin analytics (views, watch time) |
| `ratings` | PK `(profile_id, movie_id)`, `score` 1–5 | |

Enums are stored as `VARCHAR + app-level enum` so adding values needs no PG enum migration. The initial migration is hand-written and verified with `alembic check` (no drift from the models).

---

## Video pipeline

`Admin → Add title → Video`: drop a file (browser **PUTs directly to the bucket** via a presigned URL, up to 5 GB) or paste an `archive.org` URL. A Celery job then:

1. downloads the source (imports are restricted to `IMPORT_ALLOWED_HOSTS`, and every redirect hop is re-checked as an SSRF guard),
2. `ffprobe`s it and picks a ladder of **360p / 480p / 720p / 1080p** that never upscales,
3. runs one FFmpeg pass (`split` → per-rung `scale`, H.264 Main + AAC, keyframes forced on 6 s boundaries, VOD HLS),
4. writes the master playlist itself, using **measured** peak/average bitrates per rendition,
5. extracts a thumbnail, uploads to `hls/<asset-id>/` (segments `immutable`), marks the asset `ready`, and invalidates caches.

---

## Frontend highlights

- **Home:** muted auto-playing trailer hero (deferred until after LCP; disabled on mobile, reduced-motion and Save-Data), GSAP ScrollTrigger parallax, gradient fades, rotating features; Netflix-style rows with drag-to-scroll, arrow paging and staggered entrance.
- **Poster cards:** hover lift, an 800 ms hover trailer preview portalled above the carousel so it never gets clipped, shimmer skeletons, and a cross-route **poster → backdrop morph** (a persistent Framer Motion overlay in the root layout).
- **Detail:** Ken Burns backdrop, letter-by-letter title reveal, cast carousel, trailers modal, ratings, watchlist. **Watch Now** appears only for licensed titles; otherwise **Watch Trailer + Where to Watch** (TMDB / JustWatch providers).
- **Player:** custom hls.js player (lazy-loaded on `/watch` only) with ABR + manual quality, subtitles, speed, PiP, fullscreen, resume, skip intro, double-tap seek on touch, and heartbeats (with `sendBeacon` on exit). Shortcuts: `Space/K` play · `J/L ←/→` ±10 s · `↑/↓` volume · `M` mute · `F` fullscreen · `C` captions · `P` PiP · `S` skip intro · `<`/`>` speed · `0–9` seek.
- **Global:** Lenis smooth scroll synced to the GSAP ticker, glass navbar that hides on scroll-down, mobile bottom nav with animated pill, magnetic buttons, desktop-only custom cursor, `prefers-reduced-motion` respected throughout.
- **Performance:** TMDB images go through a custom `next/image` loader mapped to TMDB's CDN sizes (no optimiser cost), hero backdrop is `priority`/`fetchPriority=high`, hls.js and the player are code-split, and fonts are self-hosted via `next/font`.

---

## Tests

```bash
# Backend: 39 tests (auth rotation/reuse, rate limits, CSRF origin check, profiles, catalog,
# licensing gates, playlist signing, CDN + local-storage signatures, path traversal,
# analytics, subtitles, FFmpeg ladder/command)
npm run test:backend

# Frontend e2e (Playwright): navigation, route guards, reduced motion, instant search,
# player (real HLS stream, quality menu, shortcuts, skip intro, exit heartbeat), unlicensed-title gate
cd frontend && npx playwright install chromium webkit
npx playwright test                                    # builds + starts on :3000
E2E_BASE_URL=http://localhost:3001 npx playwright test # against an already-running `npm run dev`
# Full stack (sign-up, profiles, real playback → Continue Watching); needs `npm run dev`
# and one published film (`npm run seed -- --only "trip to the moon" --publish`):
E2E_FULL_STACK=1 E2E_BASE_URL=http://localhost:3001 npx playwright test
```

---

## Deployment

**Frontend → Vercel.** Import `frontend/`. Set `API_INTERNAL_URL=https://api.yourdomain.com` (used by rewrites at *build* time), `NEXT_PUBLIC_SITE_URL`, and optionally `NEXT_PUBLIC_GOOGLE_AUTH=true`.

**Backend → Railway / Render / VPS.** Deploy `backend/Dockerfile` three times with different start commands:
- web: default `CMD` (runs `alembic upgrade head`, then gunicorn + uvicorn workers; honours `$PORT` / `$WEB_CONCURRENCY`)
- worker: `celery -A app.workers.celery_app worker -Q transcode,default -c 2` (give it CPU and disk)
- beat: `celery -A app.workers.celery_app beat`

Production env: `ENV=prod`, `COOKIE_SECURE=true`, `TRUST_PROXY_HEADERS=true` (behind your proxy only), `FRONTEND_URL` / `CORS_ORIGINS` set to the Vercel domain, a long random `JWT_SECRET`, and `GOOGLE_REDIRECT_URI=https://<frontend>/api/v1/auth/google/callback`.

**Storage → Cloudflare R2.** `S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com`, `S3_REGION=auto`, leave `S3_PUBLIC_ENDPOINT_URL` empty. Add a bucket CORS rule so browsers can PUT uploads and hls.js can GET segments:

```json
[{ "AllowedOrigins": ["https://your-frontend.com"], "AllowedMethods": ["GET", "PUT", "HEAD"],
   "AllowedHeaders": ["*"], "MaxAgeSeconds": 3600 }]
```

To try CDN mode locally, set `STREAM_SIGNING_MODE=cdn`, `CDN_BASE_URL=http://localhost:8080/media` and a `CDN_SIGNING_SECRET` in `backend/.env`. Then give the edge read access by adding `{"name": "anonymous", "actions": ["Read:cineverse-media"]}` to `infra/seaweedfs/s3.json` and rebuilding (`up -d --build storage nginx backend`). Only do this while the storage port is private. Unsigned or expired `/media` URLs are rejected by nginx with 403/410 either way.

For CDN delivery in production, put the nginx edge (or an equivalent CDN rule that implements the same `secure_link_md5` check) in front of the bucket and set `STREAM_SIGNING_MODE=cdn`, `CDN_BASE_URL`, `CDN_SIGNING_SECRET`.

---

## Legal notes

- The seed list is made of films **widely documented as public domain in the US** (pre-1931 releases, or later titles published without notice / never renewed). Status varies by country, and restorations or new scores can carry fresh copyright. Review each title before launch; seeded licenses are scoped to `territories: ["US"]`.
- TMDB attribution is shown in the footer as TMDB's terms require; watch-provider data is credited to JustWatch.
- The admin panel will not publish without an active license and a ready asset, and playback re-checks both on every start.

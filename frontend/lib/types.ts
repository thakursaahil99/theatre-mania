// Mirrors backend/app/schemas/*.py

export interface Genre {
  id: number;
  name: string;
}

export interface MovieCard {
  id: string;
  tmdb_id: number | null;
  title: string;
  overview: string | null;
  poster_path: string | null;
  backdrop_path: string | null;
  release_date: string | null;
  vote_average: number | null;
  genre_ids: number[];
  original_language: string | null;
  streamable: boolean;
}

export interface MovieRowData {
  id: string;
  title: string;
  items: MovieCard[];
  href: string | null;
}

export interface CastMember {
  id: number;
  name: string;
  character: string | null;
  profile_path: string | null;
}

export interface Video {
  key: string;
  name: string;
  site: string;
  type: string;
}

export interface Provider {
  provider_id: number;
  provider_name: string;
  logo_path: string | null;
}

export interface WatchProviders {
  region: string;
  link: string | null;
  flatrate: Provider[];
  rent: Provider[];
  buy: Provider[];
  free: Provider[];
}

export interface Availability {
  streamable: boolean;
  license_type: string | null;
  expires_at: string | null;
  duration_seconds: number | null;
  has_subtitles: boolean;
}

export interface MovieDetail extends MovieCard {
  tagline: string | null;
  runtime: number | null;
  genres: Genre[];
  certification: string | null;
  imdb_id: string | null;
  cast: CastMember[];
  directors: { id: number; name: string; job: string }[];
  trailer: Video | null;
  videos: Video[];
  similar: MovieCard[];
  watch_providers: WatchProviders | null;
  availability: Availability;
}

export interface HomeData {
  hero: MovieDetail[];
  rows: MovieRowData[];
}

export interface MoviePage {
  page: number;
  total_pages: number;
  total_results: number;
  results: MovieCard[];
}

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  created_at: string;
}

export interface Session {
  user: User;
  active_profile_id: string | null;
}

export interface Profile {
  id: string;
  name: string;
  avatar: string;
  is_kids: boolean;
}

export interface MovieState {
  in_watchlist: boolean;
  rating: number | null;
  position_sec: number | null;
  duration_sec: number | null;
  completed: boolean;
}

export interface ProgressItem {
  movie: MovieCard;
  position_sec: number;
  duration_sec: number | null;
  completed: boolean;
  updated_at: string;
}

export interface PlaybackSubtitle {
  id: string;
  language: string;
  label: string;
  url: string;
  is_default: boolean;
}

export interface Playback {
  session_id: string;
  asset_id: string;
  movie: MovieCard;
  master_url: string;
  stream_type: "hls" | "mp4";
  duration_seconds: number | null;
  resume_position_sec: number;
  intro_start_sec: number | null;
  intro_end_sec: number | null;
  credits_start_sec: number | null;
  subtitles: PlaybackSubtitle[];
  token_expires_in: number;
}

// ---------- admin ----------

export type LicenseType = "public_domain" | "creative_commons" | "owned" | "licensed";
export type AssetStatus = "pending_upload" | "queued" | "downloading" | "processing" | "ready" | "failed";

export interface License {
  id: string;
  license_type: LicenseType;
  licensor: string | null;
  source_url: string | null;
  territories: string[];
  starts_at: string | null;
  expires_at: string | null;
  notes: string | null;
}

export interface Asset {
  id: string;
  status: AssetStatus;
  progress: number;
  source_url: string | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  renditions: { name: string; height: number; bandwidth?: number }[] | null;
  intro_start_sec: number | null;
  intro_end_sec: number | null;
  credits_start_sec: number | null;
  error: string | null;
  subtitles: { id: string; language: string; label: string; is_default: boolean }[];
  created_at: string;
  updated_at: string;
}

export interface AdminMovie {
  id: string;
  tmdb_id: number | null;
  slug: string;
  title: string;
  overview: string | null;
  tagline: string | null;
  release_date: string | null;
  runtime: number | null;
  poster_path: string | null;
  backdrop_path: string | null;
  trailer_key: string | null;
  status: "draft" | "published" | "archived";
  published_at: string | null;
  metadata_synced_at: string | null;
  license: License | null;
  license_active: boolean;
  assets: Asset[];
  created_at: string;
}

export interface AdminMovieList {
  items: AdminMovie[];
  total: number;
  page: number;
  page_size: number;
}

export interface Analytics {
  days: number;
  views: number;
  watch_hours: number;
  unique_viewers: number;
  library_size: number;
  published: number;
  expiring_soon: number;
  processing_jobs: number;
  daily: { date: string; views: number; watch_minutes: number }[];
  top_movies: { movie_id: string; title: string; poster_path: string | null; views: number; watch_minutes: number }[];
}

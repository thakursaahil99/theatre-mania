"use client";

import { MapPin, Play, Star } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { TrailerButton } from "@/components/movie/TrailerModal";
import { WatchlistButton } from "@/components/movie/WatchlistButton";
import { useAuth } from "@/components/providers/AuthProvider";
import { useLenis } from "@/components/providers/SmoothScroll";
import { Magnetic } from "@/components/ui/Magnetic";
import { api } from "@/lib/api";
import type { MovieDetail, MovieState } from "@/lib/types";
import { clock, cn } from "@/lib/utils";

export function DetailActions({ movie }: { movie: MovieDetail }) {
  const { user, activeProfile, loading } = useAuth();
  const [state, setState] = useState<MovieState | null>(null);
  const lenis = useLenis();

  useEffect(() => {
    if (!user) return setState(null);
    api<MovieState>(`/me/state/${movie.id}`).then(setState).catch(() => setState(null));
  }, [user, activeProfile, movie.id]);

  const resume = state && state.position_sec && state.position_sec > 30 && !state.completed ? state.position_sec : null;
  const scrollToProviders = () => {
    const el = document.getElementById("where-to-watch");
    if (!el) return;
    if (lenis.current) lenis.current.scrollTo(el, { offset: -90 });
    else el.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="mt-8 space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        {movie.availability.streamable ? (
          <>
            <Magnetic>
              <Link href={`/watch/${movie.id}`} className="btn-brand px-8 py-3.5 text-base">
                <Play className="size-5 fill-current" />
                {resume ? `Resume from ${clock(resume)}` : "Watch Now"}
              </Link>
            </Magnetic>
            <TrailerButton video={movie.trailer} variant="ghost" label="Trailer" />
          </>
        ) : (
          <>
            <TrailerButton video={movie.trailer} />
            <Magnetic>
              <button onClick={scrollToProviders} className="btn-ghost">
                <MapPin className="size-4" /> Where to Watch
              </button>
            </Magnetic>
          </>
        )}
        {!loading && (user ? state && <WatchlistButton key={movie.id} movieId={movie.id} initial={state.in_watchlist} />
          : <WatchlistButton movieId={movie.id} initial={false} />)}
      </div>
      {resume && state?.duration_sec ? (
        <div className="h-1 max-w-sm overflow-hidden rounded-full bg-white/15">
          <div className="h-full brand-gradient" style={{ width: `${(resume / state.duration_sec) * 100}%` }} />
        </div>
      ) : null}
      <RatingStars movieId={movie.id} value={state?.rating ?? null} onChange={(rating) => state && setState({ ...state, rating })} />
    </div>
  );
}

function RatingStars({ movieId, value, onChange }: { movieId: string; value: number | null; onChange: (v: number | null) => void }) {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [hover, setHover] = useState<number | null>(null);
  const shown = hover ?? value ?? 0;

  const rate = async (score: number) => {
    if (!user) return router.push(`/login?next=${encodeURIComponent(pathname)}`);
    const next = value === score ? null : score;
    onChange(next);
    try {
      if (next) await api(`/me/ratings/${movieId}`, { method: "PUT", json: { score: next } });
      else await api(`/me/ratings/${movieId}`, { method: "DELETE" });
    } catch {
      onChange(value);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs uppercase tracking-[0.2em] text-white/40">Your rating</span>
      <div className="flex" role="radiogroup" aria-label="Rate this title" onMouseLeave={() => setHover(null)}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} role="radio" aria-checked={value === n} aria-label={`${n} star${n > 1 ? "s" : ""}`}
            onMouseEnter={() => setHover(n)} onFocus={() => setHover(n)} onBlur={() => setHover(null)} onClick={() => rate(n)}
            className="p-1 transition-transform hover:scale-125">
            <Star className={cn("size-5 transition-colors", n <= shown ? "fill-gold text-gold" : "text-white/30")} />
          </button>
        ))}
      </div>
    </div>
  );
}

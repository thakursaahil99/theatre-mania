"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Info, Play, Star } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { WatchlistButton } from "@/components/movie/WatchlistButton";
import { getTrailer, youtubeEmbed } from "@/lib/trailers";
import type { MovieCard } from "@/lib/types";
import { rating, year } from "@/lib/utils";

/**
 * Netflix-style hover preview: after a card is hovered for 800ms, an enlarged card is
 * portalled above the carousel (so it is never clipped by overflow) and plays the trailer.
 */

interface Target {
  movie: MovieCard;
  rect: DOMRect;
}

interface PreviewApi {
  open: (t: Target) => void;
  scheduleClose: () => void;
}

const PreviewContext = createContext<PreviewApi>({ open: () => undefined, scheduleClose: () => undefined });
export const usePreview = () => useContext(PreviewContext);

export function PreviewProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<Target | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [mounted, setMounted] = useState(false);

  const cancelClose = () => closeTimer.current && clearTimeout(closeTimer.current);
  const open = useCallback((t: Target) => {
    cancelClose();
    setTarget(t);
  }, []);
  const scheduleClose = useCallback(() => {
    cancelClose();
    closeTimer.current = setTimeout(() => setTarget(null), 160);
  }, []);

  useEffect(() => {
    setMounted(true);
    const close = () => setTarget(null);
    window.addEventListener("scroll", close, { passive: true });
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close);
      window.removeEventListener("resize", close);
    };
  }, []);

  return (
    <PreviewContext.Provider value={{ open, scheduleClose }}>
      {children}
      {mounted &&
        createPortal(
          <AnimatePresence>
            {target && (
              <PreviewCard key={target.movie.id} target={target} onEnter={cancelClose} onLeave={scheduleClose}
                onNavigate={() => setTarget(null)} />
            )}
          </AnimatePresence>,
          document.body,
        )}
    </PreviewContext.Provider>
  );
}

function PreviewCard({ target, onEnter, onLeave, onNavigate }: {
  target: Target; onEnter: () => void; onLeave: () => void; onNavigate: () => void;
}) {
  const { movie, rect } = target;
  const [trailer, setTrailer] = useState<string | null>(null);
  const [videoReady, setVideoReady] = useState(false);

  useEffect(() => {
    let alive = true;
    void getTrailer(movie.id).then((t) => alive && setTrailer(t?.key ?? null));
    return () => {
      alive = false;
    };
  }, [movie.id]);

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = Math.min(Math.max(rect.width * 2.1, 320), 440);
  const height = width * 0.5625 + 148;
  const left = Math.min(Math.max(rect.left + rect.width / 2 - width / 2, 12), vw - width - 12);
  const top = Math.min(Math.max(rect.top + rect.height / 2 - height / 2, 76), vh - height - 12);
  const originX = ((rect.left + rect.width / 2 - left) / width) * 100;
  const href = `/movie/${movie.id}`;

  return (
    <motion.div
      role="dialog"
      aria-label={`${movie.title} preview`}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      className="fixed z-50 overflow-hidden rounded-2xl bg-ink-850 shadow-[0_30px_80px_-20px_rgb(0_0_0/0.9)] ring-1 ring-white/10"
      style={{ top, left, width, transformOrigin: `${originX}% 50%` }}
      initial={{ opacity: 0, scale: 0.7 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.85, transition: { duration: 0.18 } }}
      transition={{ type: "spring", stiffness: 320, damping: 28 }}
    >
      <Link href={href} onClick={onNavigate} className="relative block aspect-video overflow-hidden bg-ink-900">
        {(movie.backdrop_path || movie.poster_path) && (
          <Image src={(movie.backdrop_path || movie.poster_path)!} alt="" fill sizes="440px"
            className="animate-kenburns object-cover" />
        )}
        {trailer && (
          <iframe
            title={`${movie.title} trailer preview`}
            src={youtubeEmbed(trailer, { start: 6 })}
            allow="autoplay; encrypted-media"
            onLoad={() => setTimeout(() => setVideoReady(true), 900)}
            className="pointer-events-none absolute left-1/2 top-1/2 h-[140%] w-[140%] -translate-x-1/2 -translate-y-1/2 border-0 transition-opacity duration-700"
            style={{ opacity: videoReady ? 1 : 0 }}
          />
        )}
        <div className="absolute inset-x-0 bottom-0 h-1/2 bg-linear-to-t from-ink-850 to-transparent" />
      </Link>
      <div className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          {movie.streamable ? (
            <Link href={`/watch/${movie.id}`} onClick={onNavigate} aria-label={`Play ${movie.title}`}
              className="grid size-10 place-items-center rounded-full bg-white text-ink-950 transition hover:scale-105">
              <Play className="size-4 fill-current" />
            </Link>
          ) : null}
          <WatchlistButton movieId={movie.id} compact />
          <Link href={href} onClick={onNavigate} aria-label="More info"
            className="ml-auto grid size-10 place-items-center rounded-full border border-white/20 transition hover:border-white">
            <Info className="size-4" />
          </Link>
        </div>
        <div>
          <h3 className="line-clamp-1 font-semibold">{movie.title}</h3>
          <div className="mt-1 flex items-center gap-2 text-xs text-white/60">
            {movie.streamable && <span className="rounded bg-success/15 px-1.5 py-0.5 font-semibold text-success">FREE</span>}
            <span>{year(movie.release_date)}</span>
            <span className="inline-flex items-center gap-1">
              <Star className="size-3 fill-gold text-gold" /> {rating(movie.vote_average)}
            </span>
          </div>
          {movie.overview && <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-white/55">{movie.overview}</p>}
        </div>
      </div>
    </motion.div>
  );
}

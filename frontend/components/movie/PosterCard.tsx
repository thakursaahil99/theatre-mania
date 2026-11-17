"use client";

import { motion } from "framer-motion";
import { Star } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRef, useState } from "react";

import { useMorph } from "@/components/providers/MorphProvider";
import { usePreview } from "@/components/providers/PreviewProvider";
import { useFinePointer } from "@/lib/hooks";
import type { MovieCard } from "@/lib/types";
import { cn, rating, year } from "@/lib/utils";

const HOVER_DELAY_MS = 800;

export function PosterCard({ movie, className, priority = false, progress, sizes }: {
  movie: MovieCard;
  className?: string;
  priority?: boolean;
  progress?: number; // 0..1 for continue-watching
  sizes?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [loaded, setLoaded] = useState(false);
  const fine = useFinePointer();
  const preview = usePreview();
  const morph = useMorph();

  const onEnter = () => {
    if (!fine) return;
    timer.current = setTimeout(() => {
      if (ref.current) preview.open({ movie, rect: ref.current.getBoundingClientRect() });
    }, HOVER_DELAY_MS);
  };
  const onLeave = () => {
    if (timer.current) clearTimeout(timer.current);
    preview.scheduleClose();
  };
  const onClick = (e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || !ref.current) return;
    if (timer.current) clearTimeout(timer.current);
    const r = ref.current.getBoundingClientRect();
    morph.start({
      poster: movie.poster_path,
      backdrop: movie.backdrop_path,
      rect: { top: r.top, left: r.left, width: r.width, height: r.height },
    });
  };

  return (
    <motion.div
      ref={ref}
      className={cn("group/card relative", className)}
      whileHover={fine ? { y: -8, scale: 1.045 } : undefined}
      whileTap={{ scale: 0.97 }}
      transition={{ type: "spring", stiffness: 300, damping: 22 }}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      <Link href={`/movie/${movie.id}`} onClick={onClick} draggable={false} aria-label={movie.title}
        className="relative block aspect-[2/3] overflow-hidden rounded-xl bg-ink-800 ring-1 ring-white/5 transition-shadow duration-500 group-hover/card:shadow-[0_24px_50px_-18px_rgb(124_92_255/0.55)] group-hover/card:ring-white/20">
        {movie.poster_path && !loaded && <div className="shimmer absolute inset-0" />}
        {movie.poster_path ? (
          <Image
            src={movie.poster_path}
            alt=""
            fill
            draggable={false}
            sizes={sizes ?? "(max-width: 640px) 36vw, (max-width: 1024px) 20vw, 13vw"}
            priority={priority}
            onLoad={() => setLoaded(true)}
            className={cn("object-cover transition-[opacity,transform] duration-700 group-hover/card:scale-[1.04]",
              loaded ? "opacity-100" : "opacity-0")}
          />
        ) : (
          <div className="absolute inset-0 grid place-items-end bg-linear-to-br from-ink-700 to-ink-900 p-3">
            <span className="font-display text-xl leading-none tracking-wide text-white/80">{movie.title}</span>
          </div>
        )}

        <div className="absolute inset-x-0 bottom-0 translate-y-2 bg-linear-to-t from-black/90 via-black/40 to-transparent p-3 pt-10 opacity-0 transition duration-300 group-hover/card:translate-y-0 group-hover/card:opacity-100">
          <p className="line-clamp-2 text-sm font-semibold leading-tight">{movie.title}</p>
          <p className="mt-1 flex items-center gap-1.5 text-[11px] text-white/70">
            {year(movie.release_date)}
            <Star className="size-3 fill-gold text-gold" /> {rating(movie.vote_average)}
          </p>
        </div>

        {movie.streamable && (
          <span className="absolute left-2 top-2 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-success backdrop-blur">
            FREE
          </span>
        )}
        {progress !== undefined && (
          <div className="absolute inset-x-2 bottom-2 h-1 overflow-hidden rounded-full bg-white/20">
            <div className="h-full rounded-full brand-gradient" style={{ width: `${Math.min(100, Math.max(3, progress * 100))}%` }} />
          </div>
        )}
      </Link>
    </motion.div>
  );
}

"use client";

import { motion } from "framer-motion";
import { Star } from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";

import { DetailActions } from "@/components/movie/DetailActions";
import { TitleReveal } from "@/components/movie/TitleReveal";
import { useMorph } from "@/components/providers/MorphProvider";
import type { MovieDetail } from "@/lib/types";
import { LICENSE_LABEL, cn, rating, runtime, year } from "@/lib/utils";

const fadeUp = (delay: number) => ({
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
  transition: { delay, duration: 0.7, ease: [0.22, 1, 0.36, 1] as const },
});

export function DetailHero({ movie }: { movie: MovieDetail }) {
  const morph = useMorph();
  const [loaded, setLoaded] = useState(false);
  const backdrop = movie.backdrop_path ?? movie.poster_path;
  const { availability } = movie;

  useEffect(() => {
    if (!backdrop) morph.complete();
  }, [backdrop, morph]);

  const leavingSoon =
    availability.expires_at && new Date(availability.expires_at).getTime() - Date.now() < 30 * 86400 * 1000;

  return (
    <section className="relative min-h-[88svh] overflow-hidden" aria-label={movie.title}>
      <div className="absolute inset-0 overflow-hidden">
        {backdrop && (
          <div className="absolute inset-0 animate-kenburns will-change-transform">
            <Image src={backdrop} alt="" fill priority fetchPriority="high" sizes="100vw"
              onLoad={() => { setLoaded(true); morph.complete(); }}
              className={cn("object-cover object-top transition-opacity duration-700", loaded ? "opacity-100" : "opacity-0")} />
          </div>
        )}
        <div className="absolute inset-0 vignette-left" />
        <div className="absolute inset-0 vignette-bottom" />
        <div className="absolute inset-0 bg-ink-950/20" />
      </div>

      <div className="relative z-10 mx-auto flex min-h-[88svh] max-w-[1600px] items-end gap-10 px-4 pb-14 pt-32 md:px-12">
        {movie.poster_path && (
          <motion.div className="relative hidden aspect-[2/3] w-64 shrink-0 overflow-hidden rounded-2xl shadow-[0_40px_80px_-30px_rgb(0_0_0/0.9)] ring-1 ring-white/10 lg:block xl:w-72"
            initial={{ opacity: 0, y: 40, rotateY: -12 }} animate={{ opacity: 1, y: 0, rotateY: 0 }}
            transition={{ delay: 0.25, duration: 0.9, ease: [0.22, 1, 0.36, 1] }} style={{ transformPerspective: 1000 }}>
            <Image src={movie.poster_path} alt={`${movie.title} poster`} fill sizes="300px" className="object-cover" />
          </motion.div>
        )}

        <div className="max-w-3xl">
          <motion.div className="mb-4 flex flex-wrap gap-2" {...fadeUp(0.05)}>
            {availability.streamable ? (
              <span className="chip border-success/30 bg-success/10 text-success">
                ● Free · {LICENSE_LABEL[availability.license_type ?? ""] ?? "Licensed"}
              </span>
            ) : (
              <span className="chip">Trailer &amp; info only</span>
            )}
            {leavingSoon && (
              <span className="chip border-gold/30 bg-gold/10 text-gold">
                Leaving {new Date(availability.expires_at!).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
              </span>
            )}
            {availability.has_subtitles && <span className="chip">CC</span>}
          </motion.div>

          <TitleReveal text={movie.title} className="text-[clamp(2.6rem,7vw,6.5rem)] text-white" />
          {movie.tagline && (
            <motion.p className="mt-3 text-lg italic text-white/60" {...fadeUp(0.5)}>{movie.tagline}</motion.p>
          )}

          <motion.div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-white/75" {...fadeUp(0.6)}>
            <span className="inline-flex items-center gap-1.5 font-semibold text-white">
              <Star className="size-4 fill-gold text-gold" /> {rating(movie.vote_average)}
            </span>
            {movie.release_date && <span>{year(movie.release_date)}</span>}
            {movie.certification && <span className="rounded border border-white/30 px-1.5 text-xs">{movie.certification}</span>}
            {movie.runtime ? <span>{runtime(movie.runtime)}</span> : null}
            <span className="flex flex-wrap gap-2">
              {movie.genres.map((g) => <span key={g.id} className="chip">{g.name}</span>)}
            </span>
          </motion.div>

          {movie.overview && (
            <motion.p className="mt-6 max-w-2xl text-base leading-relaxed text-white/75 md:text-lg" {...fadeUp(0.7)}>
              {movie.overview}
            </motion.p>
          )}
          {movie.directors.length > 0 && (
            <motion.p className="mt-4 text-sm text-white/50" {...fadeUp(0.75)}>
              Directed by <span className="text-white/80">{movie.directors.map((d) => d.name).join(", ")}</span>
            </motion.p>
          )}

          <motion.div {...fadeUp(0.85)}>
            <DetailActions movie={movie} />
          </motion.div>
        </div>
      </div>
    </section>
  );
}

"use client";

import { AnimatePresence, motion } from "framer-motion";
import { gsap } from "gsap";
import { Info, Play, Star, Volume2, VolumeX } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { TitleReveal } from "@/components/movie/TitleReveal";
import { TrailerButton } from "@/components/movie/TrailerModal";
import { Magnetic } from "@/components/ui/Magnetic";
import { prefersReducedMotion, saveDataEnabled } from "@/lib/hooks";
import { youtubeEmbed, ytCommand } from "@/lib/trailers";
import type { MovieDetail } from "@/lib/types";
import { rating, runtime, year } from "@/lib/utils";

const ROTATE_MS = 9000;

export function Hero({ items }: { items: MovieDetail[] }) {
  const [index, setIndex] = useState(0);
  const [videoMounted, setVideoMounted] = useState(false);
  const [videoVisible, setVideoVisible] = useState(false);
  const [muted, setMuted] = useState(true);
  const section = useRef<HTMLElement>(null);
  const media = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const iframe = useRef<HTMLIFrameElement>(null);
  const movie = items[index];

  // Defer the trailer: the backdrop is the LCP element; YouTube loads only after it, on
  // desktop, when motion and data-saving preferences allow.
  useEffect(() => {
    setVideoMounted(false);
    setVideoVisible(false);
    setMuted(true);
    if (!movie?.trailer) return;
    const allowed = window.matchMedia("(min-width: 768px)").matches && !prefersReducedMotion() && !saveDataEnabled();
    if (!allowed) return;
    const t = setTimeout(() => setVideoMounted(true), 2000);
    return () => clearTimeout(t);
  }, [movie?.id, movie?.trailer]);

  // Rotate through hero titles only while no trailer is playing.
  useEffect(() => {
    if (items.length < 2 || videoVisible) return;
    const t = setTimeout(() => setIndex((i) => (i + 1) % items.length), ROTATE_MS);
    return () => clearTimeout(t);
  }, [index, items.length, videoVisible]);

  // Scroll-linked parallax: media drifts slower than the page, copy lifts and fades.
  useEffect(() => {
    if (prefersReducedMotion() || !section.current) return;
    const ctx = gsap.context(() => {
      gsap.to(media.current, {
        yPercent: 16, scale: 1.06, ease: "none",
        scrollTrigger: { trigger: section.current, start: "top top", end: "bottom top", scrub: true },
      });
      gsap.to(content.current, {
        yPercent: -18, opacity: 0, ease: "none",
        scrollTrigger: { trigger: section.current, start: "top top", end: "65% top", scrub: true },
      });
    }, section);
    return () => ctx.revert();
  }, []);

  // Pause the trailer when the hero scrolls out of view.
  useEffect(() => {
    if (!videoMounted || !section.current) return;
    const io = new IntersectionObserver(([e]) => ytCommand(iframe.current, e.isIntersecting ? "playVideo" : "pauseVideo"),
      { threshold: 0.25 });
    io.observe(section.current);
    return () => io.disconnect();
  }, [videoMounted]);

  if (!movie) return <HeroFallback />;
  const backdrop = movie.backdrop_path ?? movie.poster_path;

  return (
    <section ref={section} className="relative h-[92svh] min-h-[560px] w-full overflow-hidden" aria-label="Featured">
      <div ref={media} className="absolute inset-0 will-change-transform">
        <AnimatePresence mode="popLayout">
          <motion.div key={movie.id} className="absolute inset-0" initial={{ opacity: 0, scale: 1.06 }}
            animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}>
            {backdrop && (
              <Image src={backdrop} alt="" fill priority={index === 0} fetchPriority={index === 0 ? "high" : "auto"} sizes="100vw"
                className="object-cover object-[center_20%]" />
            )}
          </motion.div>
        </AnimatePresence>

        {videoMounted && movie.trailer && (
          <div className="pointer-events-none absolute inset-0 overflow-hidden transition-opacity duration-[1500ms]"
            style={{ opacity: videoVisible ? 1 : 0 }}>
            <iframe
              ref={iframe}
              title={`${movie.title} trailer`}
              src={youtubeEmbed(movie.trailer.key, { start: 4 })}
              allow="autoplay; encrypted-media"
              tabIndex={-1}
              onLoad={() => setTimeout(() => setVideoVisible(true), 1200)}
              className="absolute left-1/2 top-1/2 h-[max(100%,56.25vw)] w-[max(100%,177.78vh)] -translate-x-1/2 -translate-y-1/2 scale-[1.18] border-0"
            />
          </div>
        )}
        <div className="absolute inset-0 vignette-left" />
        <div className="absolute inset-0 vignette-bottom" />
        <div className="absolute inset-x-0 top-0 h-40 bg-linear-to-b from-ink-950/70 to-transparent" />
      </div>

      <div ref={content} className="relative z-10 flex h-full flex-col justify-end px-4 pb-[14vh] md:px-12 md:pb-[18vh]">
        <AnimatePresence mode="wait">
          <motion.div key={movie.id} className="max-w-2xl" exit={{ opacity: 0, y: -16, transition: { duration: 0.35 } }}>
            <motion.div className="mb-4 flex flex-wrap items-center gap-2" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 }}>
              {movie.streamable ? (
                <span className="chip border-success/30 bg-success/10 text-success">● Free to watch now</span>
              ) : (
                <span className="chip">#{index + 1} Trending this week</span>
              )}
              {movie.certification && <span className="chip">{movie.certification}</span>}
            </motion.div>

            <TitleReveal text={movie.title} className="text-[clamp(2.8rem,8vw,7.5rem)] text-white drop-shadow-[0_6px_30px_rgb(0_0_0/0.5)]" />

            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.55, duration: 0.7 }}>
              <p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-white/75">
                <span>{year(movie.release_date)}</span>
                <span className="inline-flex items-center gap-1"><Star className="size-3.5 fill-gold text-gold" />{rating(movie.vote_average)}</span>
                {movie.runtime ? <span>{runtime(movie.runtime)}</span> : null}
                {movie.genres.slice(0, 3).map((g) => <span key={g.id} className="text-white/55">{g.name}</span>)}
              </p>
              {movie.overview && <p className="mt-4 line-clamp-3 max-w-xl text-base leading-relaxed text-white/70 md:text-lg">{movie.overview}</p>}

              <div className="mt-7 flex flex-wrap items-center gap-3">
                {movie.streamable ? (
                  <Magnetic>
                    <Link href={`/watch/${movie.id}`} className="btn-primary px-8"><Play className="size-4 fill-current" /> Play</Link>
                  </Magnetic>
                ) : (
                  <TrailerButton video={movie.trailer} />
                )}
                <Magnetic>
                  <Link href={`/movie/${movie.id}`} className="btn-ghost"><Info className="size-4" /> More Info</Link>
                </Magnetic>
              </div>
            </motion.div>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="absolute bottom-[8vh] right-4 z-10 flex items-center gap-4 md:right-12">
        {videoVisible && (
          <button
            onClick={() => {
              ytCommand(iframe.current, muted ? "unMute" : "mute");
              setMuted((m) => !m);
            }}
            aria-label={muted ? "Unmute trailer" : "Mute trailer"}
            className="grid size-11 place-items-center rounded-full border border-white/30 bg-black/30 backdrop-blur transition hover:border-white"
          >
            {muted ? <VolumeX className="size-5" /> : <Volume2 className="size-5" />}
          </button>
        )}
        {items.length > 1 && (
          <div className="flex gap-1.5" role="tablist" aria-label="Featured titles">
            {items.map((m, i) => (
              <button key={m.id} role="tab" aria-selected={i === index} aria-label={m.title} onClick={() => setIndex(i)}
                className="relative h-1 w-7 overflow-hidden rounded-full bg-white/25">
                {i === index && (
                  <motion.span className="absolute inset-y-0 left-0 bg-white" initial={{ width: "0%" }}
                    animate={{ width: "100%" }} transition={{ duration: videoVisible ? 0.3 : ROTATE_MS / 1000, ease: "linear" }} />
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function HeroFallback() {
  return (
    <section className="relative grid h-[80svh] min-h-[520px] place-items-center overflow-hidden px-4 text-center grain">
      <div className="absolute -left-1/4 top-1/4 size-[60vw] rounded-full bg-accent/25 blur-[120px]" />
      <div className="absolute -right-1/4 top-0 size-[50vw] rounded-full bg-accent-2/20 blur-[120px]" />
      <div className="relative max-w-2xl">
        <TitleReveal text="Cinema, without the noise." className="text-[clamp(2.6rem,8vw,6rem)] text-white" />
        <p className="mx-auto mt-5 max-w-lg text-white/65">
          Stream timeless public-domain classics for free and discover what to watch next, with no ads.
        </p>
        <Link href="/browse/free" className="btn-brand mt-8">Explore free films</Link>
      </div>
    </section>
  );
}

"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef } from "react";

import { PosterCard } from "@/components/movie/PosterCard";
import type { MovieCard } from "@/lib/types";

export function MovieGrid({ movies, onEndReached, renderExtra }: {
  movies: MovieCard[];
  onEndReached?: () => void;
  renderExtra?: (m: MovieCard) => React.ReactNode;
}) {
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!onEndReached || !sentinel.current) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && onEndReached(), { rootMargin: "600px" });
    io.observe(sentinel.current);
    return () => io.disconnect();
  }, [onEndReached]);

  return (
    <>
      <motion.ul layout className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        <AnimatePresence mode="popLayout">
          {movies.map((m, i) => (
            <motion.li
              key={m.id}
              layout
              initial={{ opacity: 0, y: 24, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
              transition={{ duration: 0.45, delay: Math.min(i % 20, 12) * 0.03, ease: [0.22, 1, 0.36, 1] }}
            >
              <PosterCard movie={m} sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 16vw" />
              {renderExtra?.(m)}
            </motion.li>
          ))}
        </AnimatePresence>
      </motion.ul>
      {onEndReached && <div ref={sentinel} aria-hidden className="h-px" />}
    </>
  );
}

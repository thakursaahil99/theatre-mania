"use client";

import { AnimatePresence, motion } from "framer-motion";
import Image from "next/image";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Cross-route "shared element" transition: a poster card morphs into the detail page's
 * full-bleed backdrop. The overlay lives in the root layout, so it survives the route
 * change; the detail page calls `complete()` once its own backdrop has painted.
 */

interface MorphSource {
  poster: string | null;
  backdrop: string | null;
  rect: { top: number; left: number; width: number; height: number };
}

interface MorphApi {
  start: (src: MorphSource) => void;
  complete: () => void;
  active: boolean;
}

const MorphContext = createContext<MorphApi>({ start: () => undefined, complete: () => undefined, active: false });
export const useMorph = () => useContext(MorphContext);

const EASE = [0.22, 1, 0.36, 1] as const;

export function MorphProvider({ children }: { children: ReactNode }) {
  const [source, setSource] = useState<MorphSource | null>(null);
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const complete = useCallback(() => {
    if (timeout.current) clearTimeout(timeout.current);
    // Let the detail backdrop sit under the overlay for a beat, then dissolve.
    setTimeout(() => setSource(null), 120);
  }, []);

  const start = useCallback((src: MorphSource) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    setSource(src);
    if (timeout.current) clearTimeout(timeout.current);
    timeout.current = setTimeout(() => setSource(null), 2200); // safety net
  }, []);

  useEffect(() => () => void (timeout.current && clearTimeout(timeout.current)), []);

  return (
    <MorphContext.Provider value={{ start, complete, active: source !== null }}>
      {children}
      <AnimatePresence>
        {source && (
          <motion.div
            key="morph"
            aria-hidden
            className="pointer-events-none fixed z-[60] overflow-hidden bg-ink-900"
            initial={{ ...source.rect, borderRadius: 14, opacity: 1 }}
            animate={{ top: 0, left: 0, width: "100vw", height: "88vh", borderRadius: 0 }}
            exit={{ opacity: 0, transition: { duration: 0.45 } }}
            transition={{ duration: 0.7, ease: EASE }}
          >
            {source.backdrop && (
              <motion.div className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.1 }}>
                <Image src={source.backdrop} alt="" fill sizes="100vw" className="object-cover" priority />
              </motion.div>
            )}
            {source.poster && (
              <motion.div className="absolute inset-0" initial={{ opacity: 1 }} animate={{ opacity: source.backdrop ? 0 : 1 }}
                transition={{ duration: 0.45, delay: 0.15 }}>
                <Image src={source.poster} alt="" fill sizes="30vw" className="object-cover" />
              </motion.div>
            )}
            <div className="absolute inset-0 vignette-bottom opacity-80" />
          </motion.div>
        )}
      </AnimatePresence>
    </MorphContext.Provider>
  );
}

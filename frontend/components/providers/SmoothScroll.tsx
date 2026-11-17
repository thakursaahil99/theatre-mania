"use client";

import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";

gsap.registerPlugin(ScrollTrigger);

const LenisContext = createContext<{ current: Lenis | null }>({ current: null });
export const useLenis = () => useContext(LenisContext);

let inAppNavigation = false;
/**
 * True once the user has navigated within Theatre Mania during this page load. `history.length`
 * can't tell us that: it also counts other sites and the tab's initial about:blank.
 */
export const hasInAppHistory = () => inAppNavigation;

/** Lenis smooth scrolling driven by GSAP's ticker so ScrollTrigger stays perfectly in sync. */
export function SmoothScroll({ children }: { children: ReactNode }) {
  const lenisRef = useRef<Lenis | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduce.matches) return;

    const lenis = new Lenis({ lerp: 0.11, wheelMultiplier: 0.95, smoothWheel: true });
    lenisRef.current = lenis;
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(tick);
      lenis.destroy();
      lenisRef.current = null;
    };
  }, []);

  // New page → start at the top (Lenis keeps its own scroll position).
  const firstPath = useRef(true);
  useEffect(() => {
    if (firstPath.current) firstPath.current = false;
    else inAppNavigation = true;
    lenisRef.current?.scrollTo(0, { immediate: true });
    requestAnimationFrame(() => ScrollTrigger.refresh());
  }, [pathname]);

  return <LenisContext.Provider value={lenisRef}>{children}</LenisContext.Provider>;
}

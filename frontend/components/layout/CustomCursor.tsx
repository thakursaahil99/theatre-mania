"use client";

import { motion, useMotionValue, useSpring } from "framer-motion";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

/** Desktop-only dot + trailing ring. Grows over interactive elements, hides in the player. */
export function CustomCursor() {
  const [enabled, setEnabled] = useState(false);
  const [variant, setVariant] = useState<"default" | "hover" | "magnetic">("default");
  const [down, setDown] = useState(false);
  const [visible, setVisible] = useState(false);
  const pathname = usePathname();
  const x = useMotionValue(-100);
  const y = useMotionValue(-100);
  const rx = useSpring(x, { stiffness: 380, damping: 32, mass: 0.6 });
  const ry = useSpring(y, { stiffness: 380, damping: 32, mass: 0.6 });

  const inPlayer = pathname.startsWith("/watch");

  useEffect(() => {
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setEnabled(fine.matches && !reduce.matches);
    update();
    fine.addEventListener("change", update);
    reduce.addEventListener("change", update);
    return () => {
      fine.removeEventListener("change", update);
      reduce.removeEventListener("change", update);
    };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (!enabled || inPlayer) {
      root.classList.remove("has-cursor");
      return;
    }
    root.classList.add("has-cursor");
    const move = (e: PointerEvent) => {
      x.set(e.clientX);
      y.set(e.clientY);
      setVisible(true);
      const el = e.target as HTMLElement | null;
      if (el?.closest("[data-cursor='magnetic']")) setVariant("magnetic");
      else if (el?.closest("a, button, [role='button'], input[type='range'], select, label")) setVariant("hover");
      else setVariant("default");
    };
    const leave = () => setVisible(false);
    const pressed = () => setDown(true);
    const released = () => setDown(false);
    window.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerleave", leave);
    window.addEventListener("pointerdown", pressed);
    window.addEventListener("pointerup", released);
    return () => {
      root.classList.remove("has-cursor");
      window.removeEventListener("pointermove", move);
      document.removeEventListener("pointerleave", leave);
      window.removeEventListener("pointerdown", pressed);
      window.removeEventListener("pointerup", released);
    };
  }, [enabled, inPlayer, x, y]);

  if (!enabled || inPlayer) return null;
  const ring = variant === "magnetic" ? 64 : variant === "hover" ? 46 : 30;

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-[100]" style={{ opacity: visible ? 1 : 0 }}>
      <motion.div className="absolute left-0 top-0 size-1.5 rounded-full bg-white mix-blend-difference"
        style={{ x, y, translateX: "-50%", translateY: "-50%" }} />
      <motion.div
        className="absolute left-0 top-0 rounded-full border border-white/70 mix-blend-difference"
        style={{ x: rx, y: ry, translateX: "-50%", translateY: "-50%" }}
        animate={{ width: ring, height: ring, scale: down ? 0.8 : 1,
          backgroundColor: variant === "magnetic" ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0)" }}
        transition={{ type: "spring", stiffness: 300, damping: 24 }}
      />
    </div>
  );
}

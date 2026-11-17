"use client";

import { motion, type Variants } from "framer-motion";

import { cn } from "@/lib/utils";

const letter: Variants = {
  hidden: { y: "115%", rotate: 6, opacity: 0 },
  show: { y: "0%", rotate: 0, opacity: 1, transition: { duration: 0.85, ease: [0.22, 1, 0.36, 1] } },
};

/** Letter-by-letter masked reveal. Screen readers get the plain title via aria-label. */
export function TitleReveal({ text, className, delay = 0.1, as = "h1" }: {
  text: string;
  className?: string;
  delay?: number;
  as?: "h1" | "h2";
}) {
  const Tag = as === "h1" ? motion.h1 : motion.h2;
  const words = text.split(" ");
  const stagger = Math.max(0.012, Math.min(0.04, 0.9 / text.length));
  return (
    <Tag
      key={text}
      aria-label={text}
      className={cn("font-display leading-[0.92] tracking-wide", className)}
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: stagger, delayChildren: delay } } }}
    >
      {words.map((word, wi) => (
        <span key={wi} aria-hidden className="inline-block overflow-hidden whitespace-nowrap pb-[0.06em] align-bottom">
          {Array.from(word).map((ch, ci) => (
            <motion.span key={ci} variants={letter} className="inline-block origin-bottom-left">
              {ch}
            </motion.span>
          ))}
          {wi < words.length - 1 && <span className="inline-block">&nbsp;</span>}
        </span>
      ))}
    </Tag>
  );
}

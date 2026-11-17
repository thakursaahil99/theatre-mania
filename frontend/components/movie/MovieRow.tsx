"use client";

import { motion, type Variants } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { PosterCard } from "@/components/movie/PosterCard";
import { CARD_WIDTH } from "@/components/ui/Skeleton";
import type { MovieCard } from "@/lib/types";
import { cn } from "@/lib/utils";

const list: Variants = { hidden: {}, show: { transition: { staggerChildren: 0.05, delayChildren: 0.05 } } };
const item: Variants = {
  hidden: { opacity: 0, y: 36, scale: 0.96 },
  show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] } },
};

/** Horizontal carousel: native touch/trackpad scroll + mouse drag + arrow paging. */
export function Carousel({ children, label }: { children: ReactNode; label: string }) {
  const ref = useRef<HTMLUListElement>(null);
  const drag = useRef({ active: false, moved: false, startX: 0, startLeft: 0 });
  const [edges, setEdges] = useState({ start: true, end: false });

  const updateEdges = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setEdges({ start: el.scrollLeft < 8, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 8 });
  }, []);

  useEffect(() => {
    updateEdges();
    window.addEventListener("resize", updateEdges);
    return () => window.removeEventListener("resize", updateEdges);
  }, [updateEdges]);

  const page = (dir: 1 | -1) => ref.current?.scrollBy({ left: dir * ref.current.clientWidth * 0.85, behavior: "smooth" });

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.pointerType !== "mouse" || e.button !== 0 || !ref.current) return;
    drag.current = { active: true, moved: false, startX: e.clientX, startLeft: ref.current.scrollLeft };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    const el = ref.current;
    if (!d.active || !el) return;
    const dx = e.clientX - d.startX;
    if (!d.moved && Math.abs(dx) > 6) {
      d.moved = true;
      el.style.scrollSnapType = "none";
      el.style.cursor = "grabbing";
    }
    if (d.moved) el.scrollLeft = d.startLeft - dx;
  };
  const endDrag = () => {
    const el = ref.current;
    if (!drag.current.active || !el) return;
    drag.current.active = false;
    el.style.scrollSnapType = "";
    el.style.cursor = "";
  };
  // Swallow the click that ends a drag so we don't navigate.
  const onClickCapture = (e: React.MouseEvent) => {
    if (drag.current.moved) {
      e.preventDefault();
      e.stopPropagation();
      drag.current.moved = false;
    }
  };

  return (
    <div className="group/row relative">
      <motion.ul
        ref={ref}
        aria-label={label}
        className="no-scrollbar flex snap-x snap-proximity gap-3 overflow-x-auto scroll-px-4 px-4 py-6 md:gap-4 md:scroll-px-12 md:px-12"
        variants={list}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "0px 0px -12% 0px" }}
        onScroll={updateEdges}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
        onClickCapture={onClickCapture}
        onDragStart={(e) => e.preventDefault()}
      >
        {children}
      </motion.ul>
      <ArrowButton side="left" hidden={edges.start} onClick={() => page(-1)} />
      <ArrowButton side="right" hidden={edges.end} onClick={() => page(1)} />
    </div>
  );
}

export function CarouselItem({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.li variants={item} className={cn("shrink-0 snap-start", className)}>
      {children}
    </motion.li>
  );
}

function ArrowButton({ side, hidden, onClick }: { side: "left" | "right"; hidden: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label={side === "left" ? "Scroll left" : "Scroll right"}
      tabIndex={-1}
      className={cn(
        "absolute inset-y-6 z-10 hidden w-12 items-center justify-center bg-linear-to-r text-white opacity-0 transition duration-300 md:flex",
        side === "left" ? "left-0 from-ink-950/90 to-transparent" : "right-0 from-transparent to-ink-950/90",
        hidden ? "pointer-events-none" : "group-hover/row:opacity-100",
      )}
    >
      <span className="grid size-10 place-items-center rounded-full glass transition hover:scale-110">
        {side === "left" ? <ChevronLeft className="size-5" /> : <ChevronRight className="size-5" />}
      </span>
    </button>
  );
}

export function RowHeader({ title, href }: { title: string; href?: string | null }) {
  return (
    <div className="flex items-end justify-between px-4 md:px-12">
      <h2 className="font-display text-2xl tracking-wide text-white md:text-3xl">{title}</h2>
      {href && (
        <Link href={href} className="group flex items-center gap-1 text-sm text-white/55 transition hover:text-white">
          See all
          <ChevronRight className="size-4 transition-transform group-hover:translate-x-1" />
        </Link>
      )}
    </div>
  );
}

export function MovieRow({ title, items, href, priority = false }: {
  title: string;
  items: MovieCard[];
  href?: string | null;
  priority?: boolean;
}) {
  if (!items.length) return null;
  return (
    <section aria-label={title}>
      <RowHeader title={title} href={href} />
      <Carousel label={title}>
        {items.map((m, i) => (
          <CarouselItem key={m.id} className={CARD_WIDTH}>
            <PosterCard movie={m} priority={priority && i < 6} />
          </CarouselItem>
        ))}
      </Carousel>
    </section>
  );
}

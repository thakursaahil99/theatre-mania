"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Check, Plus } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/providers/AuthProvider";
import { api } from "@/lib/api";
import type { MovieState } from "@/lib/types";
import { cn } from "@/lib/utils";

const EVENT = "cv:watchlist";

export function WatchlistButton({ movieId, compact = false, initial }: { movieId: string; compact?: boolean; initial?: boolean }) {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [inList, setInList] = useState<boolean>(initial ?? false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user || initial !== undefined) return;
    let alive = true;
    api<MovieState>(`/me/state/${movieId}`)
      .then((s) => alive && setInList(s.in_watchlist))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [user, movieId, initial]);

  useEffect(() => {
    const sync = (e: Event) => {
      const d = (e as CustomEvent<{ id: string; inList: boolean }>).detail;
      if (d.id === movieId) setInList(d.inList);
    };
    window.addEventListener(EVENT, sync);
    return () => window.removeEventListener(EVENT, sync);
  }, [movieId]);

  const toggle = async () => {
    if (!user) return router.push(`/login?next=${encodeURIComponent(pathname)}`);
    const next = !inList;
    setInList(next);
    setBusy(true);
    try {
      await api(`/me/watchlist/${movieId}`, { method: next ? "PUT" : "DELETE" });
      window.dispatchEvent(new CustomEvent(EVENT, { detail: { id: movieId, inList: next } }));
    } catch {
      setInList(!next);
    } finally {
      setBusy(false);
    }
  };

  const icon = (
    <AnimatePresence mode="wait" initial={false}>
      <motion.span key={inList ? "in" : "out"} initial={{ rotate: -90, scale: 0.4, opacity: 0 }}
        animate={{ rotate: 0, scale: 1, opacity: 1 }} exit={{ rotate: 90, scale: 0.4, opacity: 0 }} transition={{ duration: 0.2 }}
        className="grid place-items-center">
        {inList ? <Check className="size-4" /> : <Plus className="size-4" />}
      </motion.span>
    </AnimatePresence>
  );

  if (compact) {
    return (
      <button onClick={toggle} disabled={busy} aria-pressed={inList} aria-label={inList ? "Remove from My List" : "Add to My List"}
        className={cn("grid size-10 place-items-center rounded-full border transition",
          inList ? "border-white bg-white/10" : "border-white/20 hover:border-white")}>
        {icon}
      </button>
    );
  }
  return (
    <button onClick={toggle} disabled={busy} aria-pressed={inList} className="btn-ghost">
      {icon}
      {inList ? "In My List" : "My List"}
    </button>
  );
}

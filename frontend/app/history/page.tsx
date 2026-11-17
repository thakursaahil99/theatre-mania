"use client";

import { motion } from "framer-motion";
import { Check, Play, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

import { TitleReveal } from "@/components/movie/TitleReveal";
import { useAuth } from "@/components/providers/AuthProvider";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { ProgressItem } from "@/lib/types";
import { clock } from "@/lib/utils";

export default function HistoryPage() {
  const { activeProfile } = useAuth();
  const [items, setItems] = useState<ProgressItem[] | null>(null);

  useEffect(() => {
    if (activeProfile) api<ProgressItem[]>("/me/history").then(setItems).catch(() => setItems([]));
  }, [activeProfile]);

  const remove = async (id: string) => {
    setItems((list) => list?.filter((i) => i.movie.id !== id) ?? null);
    await api(`/me/history/${id}`, { method: "DELETE" }).catch(() => undefined);
  };

  return (
    <div className="min-h-svh px-4 pb-24 pt-32 md:px-12">
      <div className="mx-auto max-w-4xl">
        <TitleReveal text="Watch History" className="text-[clamp(2.6rem,6vw,5rem)]" />
        <ul className="mt-10 space-y-3">
          {items === null && Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
          {items?.length === 0 && <p className="py-20 text-center text-white/50">Nothing watched yet.</p>}
          {items?.map((item, i) => {
            const pct = item.duration_sec ? (item.position_sec / item.duration_sec) * 100 : 0;
            return (
              <motion.li key={item.movie.id} layout initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                className="group flex items-center gap-4 rounded-2xl border border-white/5 bg-white/[0.02] p-3 transition hover:bg-white/[0.05]">
                <Link href={`/movie/${item.movie.id}`} className="relative aspect-video w-36 shrink-0 overflow-hidden rounded-xl bg-ink-800 md:w-48">
                  {(item.movie.backdrop_path || item.movie.poster_path) && (
                    <Image src={(item.movie.backdrop_path || item.movie.poster_path)!} alt="" fill sizes="200px" className="object-cover" />
                  )}
                  {!item.completed && <div className="absolute inset-x-0 bottom-0 h-1 bg-white/20"><div className="h-full brand-gradient" style={{ width: `${pct}%` }} /></div>}
                </Link>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{item.movie.title}</p>
                  <p className="mt-1 text-sm text-white/50">
                    {item.completed ? (
                      <span className="inline-flex items-center gap-1 text-success"><Check className="size-3.5" /> Watched</span>
                    ) : `${clock(item.position_sec)} of ${clock(item.duration_sec ?? 0)}`}
                    <span className="ml-2 text-white/30">· {new Date(item.updated_at).toLocaleDateString()}</span>
                  </p>
                </div>
                {item.movie.streamable && (
                  <Link href={`/watch/${item.movie.id}`} aria-label={`Play ${item.movie.title}`}
                    className="grid size-11 shrink-0 place-items-center rounded-full bg-white text-ink-950 transition hover:scale-105">
                    <Play className="size-4 fill-current" />
                  </Link>
                )}
                <button onClick={() => remove(item.movie.id)} aria-label={`Remove ${item.movie.title} from history`}
                  className="grid size-10 shrink-0 place-items-center rounded-full text-white/40 opacity-100 transition hover:bg-white/10 hover:text-white md:opacity-0 md:group-hover:opacity-100">
                  <X className="size-4" />
                </button>
              </motion.li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

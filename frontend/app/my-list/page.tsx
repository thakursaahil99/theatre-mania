"use client";

import { Bookmark } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { MovieGrid } from "@/components/movie/MovieGrid";
import { TitleReveal } from "@/components/movie/TitleReveal";
import { useAuth } from "@/components/providers/AuthProvider";
import { GridSkeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { MovieCard } from "@/lib/types";

export default function MyListPage() {
  const { activeProfile } = useAuth();
  const [items, setItems] = useState<MovieCard[] | null>(null);

  useEffect(() => {
    if (!activeProfile) return;
    api<MovieCard[]>("/me/watchlist").then(setItems).catch(() => setItems([]));
    const onChange = (e: Event) => {
      const d = (e as CustomEvent<{ id: string; inList: boolean }>).detail;
      if (!d.inList) setItems((list) => list?.filter((m) => m.id !== d.id) ?? null);
    };
    window.addEventListener("cv:watchlist", onChange);
    return () => window.removeEventListener("cv:watchlist", onChange);
  }, [activeProfile]);

  return (
    <div className="min-h-svh px-4 pb-24 pt-32 md:px-12">
      <div className="mx-auto max-w-[1600px]">
        <TitleReveal text="My List" className="text-[clamp(2.6rem,6vw,5rem)]" />
        <p className="mt-2 text-white/50">{activeProfile ? `Saved by ${activeProfile.name}` : ""}</p>
        <div className="mt-10">
          {items === null ? (
            <GridSkeleton />
          ) : items.length === 0 ? (
            <div className="py-24 text-center">
              <Bookmark className="mx-auto size-10 text-white/25" />
              <p className="mt-4 text-lg text-white/70">Your list is empty.</p>
              <p className="mt-1 text-sm text-white/45">Tap “My List” on any title to save it for later.</p>
              <Link href="/browse/free" className="btn-brand mt-8">Browse free films</Link>
            </div>
          ) : (
            <MovieGrid movies={items} />
          )}
        </div>
      </div>
    </div>
  );
}

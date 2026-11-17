"use client";

import { useEffect, useState } from "react";

import { Carousel, CarouselItem, RowHeader } from "@/components/movie/MovieRow";
import { PosterCard } from "@/components/movie/PosterCard";
import { useAuth } from "@/components/providers/AuthProvider";
import { CARD_WIDTH } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { ProgressItem } from "@/lib/types";

export function ContinueWatching() {
  const { user, activeProfile } = useAuth();
  const [items, setItems] = useState<ProgressItem[]>([]);

  useEffect(() => {
    if (!user || !activeProfile) return setItems([]);
    let alive = true;
    api<ProgressItem[]>("/me/continue-watching", { headers: { "X-Profile-Id": activeProfile.id } })
      .then((r) => alive && setItems(r))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [user, activeProfile]);

  if (!items.length) return null;
  return (
    <section aria-label="Continue watching">
      <RowHeader title={`Continue Watching for ${activeProfile?.name ?? "you"}`} />
      <Carousel label="Continue watching">
        {items.map((p) => (
          <CarouselItem key={p.movie.id} className={CARD_WIDTH}>
            <PosterCard movie={p.movie} progress={p.duration_sec ? p.position_sec / p.duration_sec : 0} />
          </CarouselItem>
        ))}
      </Carousel>
    </section>
  );
}

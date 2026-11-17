"use client";

import { ExternalLink, Play } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { Carousel, CarouselItem, RowHeader } from "@/components/movie/MovieRow";
import { TrailerModal } from "@/components/movie/TrailerModal";
import type { CastMember, Provider, Video, WatchProviders } from "@/lib/types";

export function CastCarousel({ cast }: { cast: CastMember[] }) {
  return (
    <section aria-label="Cast">
      <RowHeader title="Top Cast" />
      <Carousel label="Cast">
        {cast.map((c) => (
          <CarouselItem key={`${c.id}-${c.character}`} className="w-28 md:w-36">
            <div className="group text-center">
              <div className="relative mx-auto aspect-square w-full overflow-hidden rounded-full bg-ink-800 ring-1 ring-white/10 transition duration-500 group-hover:ring-accent/60">
                {c.profile_path ? (
                  <Image src={c.profile_path} alt={c.name} fill sizes="150px"
                    className="object-cover grayscale-[35%] transition duration-500 group-hover:scale-110 group-hover:grayscale-0" />
                ) : (
                  <span className="grid size-full place-items-center font-display text-3xl text-white/30">
                    {c.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
                  </span>
                )}
              </div>
              <p className="mt-3 line-clamp-1 text-sm font-medium">{c.name}</p>
              {c.character && <p className="line-clamp-1 text-xs text-white/45">{c.character}</p>}
            </div>
          </CarouselItem>
        ))}
      </Carousel>
    </section>
  );
}

export function VideosRow({ videos }: { videos: Video[] }) {
  const [active, setActive] = useState<Video | null>(null);
  return (
    <section aria-label="Trailers and clips">
      <RowHeader title="Trailers & Clips" />
      <Carousel label="Trailers and clips">
        {videos.map((v) => (
          <CarouselItem key={v.key} className="w-[72vw] sm:w-[44vw] md:w-[30vw] lg:w-[22vw]">
            <button onClick={() => setActive(v)} className="group block w-full text-left">
              <div className="relative aspect-video overflow-hidden rounded-xl bg-ink-800 ring-1 ring-white/5">
                <Image src={`https://i.ytimg.com/vi/${v.key}/hqdefault.jpg`} alt="" fill sizes="(max-width: 768px) 72vw, 22vw"
                  className="object-cover transition duration-700 group-hover:scale-105" />
                <span className="absolute inset-0 grid place-items-center bg-black/30 transition group-hover:bg-black/10">
                  <span className="grid size-12 place-items-center rounded-full bg-white/90 text-ink-950 transition group-hover:scale-110">
                    <Play className="size-5 fill-current" />
                  </span>
                </span>
              </div>
              <p className="mt-2 line-clamp-1 text-sm text-white/80">{v.name}</p>
              <p className="text-xs text-white/40">{v.type}</p>
            </button>
          </CarouselItem>
        ))}
      </Carousel>
      <TrailerModal video={active} open={!!active} onClose={() => setActive(null)} />
    </section>
  );
}

function ProviderGroup({ label, items }: { label: string; items: Provider[] }) {
  if (!items.length) return null;
  return (
    <div>
      <p className="mb-3 text-xs uppercase tracking-[0.2em] text-white/40">{label}</p>
      <ul className="flex flex-wrap gap-3">
        {items.map((p) => (
          <li key={p.provider_id} title={p.provider_name}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] py-1.5 pl-1.5 pr-3 text-sm">
            {p.logo_path && <Image src={p.logo_path} alt="" width={32} height={32} className="rounded-lg" />}
            {p.provider_name}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function WhereToWatch({ providers, title }: { providers: WatchProviders | null; title: string }) {
  const has = providers && (providers.flatrate.length || providers.rent.length || providers.buy.length || providers.free.length);
  return (
    <section id="where-to-watch" aria-label="Where to watch" className="scroll-mt-24 px-4 md:px-12">
      <div className="glass rounded-3xl p-6 md:p-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="font-display text-3xl tracking-wide">Where to Watch</h2>
            <p className="mt-1 text-sm text-white/50">
              {title} isn&apos;t in our free library. Here&apos;s where to stream it legally
              {providers ? ` in ${providers.region}` : ""}.
            </p>
          </div>
          {providers?.link && (
            <a href={providers.link} target="_blank" rel="noreferrer" className="btn-ghost px-4 py-2 text-xs">
              All options <ExternalLink className="size-3.5" />
            </a>
          )}
        </div>
        {has ? (
          <div className="mt-8 grid gap-8 md:grid-cols-2">
            <ProviderGroup label="Stream" items={providers!.flatrate} />
            <ProviderGroup label="Free with ads" items={providers!.free} />
            <ProviderGroup label="Rent" items={providers!.rent} />
            <ProviderGroup label="Buy" items={providers!.buy} />
          </div>
        ) : (
          <p className="mt-8 text-white/60">No streaming options are listed for your region right now.</p>
        )}
        <p className="mt-8 text-[11px] text-white/35">Availability data provided by JustWatch via TMDB.</p>
      </div>
    </section>
  );
}

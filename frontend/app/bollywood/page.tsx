import type { Metadata } from "next";
import Link from "next/link";

import { Hero } from "@/components/home/Hero";
import { MovieRow } from "@/components/movie/MovieRow";
import { TitleReveal } from "@/components/movie/TitleReveal";
import { REVALIDATE, serverFetch } from "@/lib/server-api";
import type { HomeData } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Bollywood",
  description: "Trending, new and classic Hindi films, with trailers, cast and where to watch them in India.",
};

export default async function BollywoodPage() {
  const data = await serverFetch<HomeData>("/movies/bollywood", REVALIDATE.availability);
  const rows = data?.rows ?? [];

  if (!rows.length) {
    return (
      <div className="relative grid min-h-[80svh] place-items-center overflow-hidden px-4 text-center grain">
        <div className="absolute -left-1/4 top-1/4 size-[50vw] rounded-full bg-accent-2/20 blur-[120px]" />
        <div className="relative max-w-xl">
          <TitleReveal text="Bollywood" className="text-[clamp(3rem,9vw,6.5rem)] text-white" />
          <p className="mt-4 text-white/60">
            {data
              ? "Bollywood rows load from TMDB. Add a free TMDB key (TMDB_READ_TOKEN in backend/.env) and restart the API."
              : "We couldn't reach the catalog right now. Please try again in a moment."}
          </p>
          <Link href="/browse/free" className="btn-brand mt-8">Browse free films</Link>
        </div>
      </div>
    );
  }

  return (
    <>
      <Hero items={data?.hero ?? []} />
      <div className="relative z-10 -mt-[10vh] space-y-6 md:space-y-10">
        {rows.map((row, i) => (
          <MovieRow key={row.id} title={row.title} items={row.items} href={row.href} priority={i === 0} />
        ))}
      </div>
    </>
  );
}

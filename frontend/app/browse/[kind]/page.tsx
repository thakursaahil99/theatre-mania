import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BrowseGrid } from "@/components/search/BrowseGrid";
import { TitleReveal } from "@/components/movie/TitleReveal";
import { REVALIDATE, serverFetch } from "@/lib/server-api";
import type { Genre, MoviePage } from "@/lib/types";

export const dynamic = "force-dynamic";

const KINDS: Record<string, { title: string; blurb: string }> = {
  free: { title: "Free to Watch", blurb: "Public-domain and licensed films you can stream right now, free and ad-free." },
  trending: { title: "Trending This Week", blurb: "What the world is watching." },
  new: { title: "New Releases", blurb: "Fresh in theaters and on streaming." },
  top_rated: { title: "Top Rated", blurb: "The highest-rated films of all time." },
  popular: { title: "Popular", blurb: "Crowd favourites." },
};

// Mirrors backend/app/services/bollywood.py ROWS.
const BOLLYWOOD: Record<string, string> = {
  trending: "Trending in Bollywood",
  new: "New Bollywood Releases",
  top: "Bollywood's Highest Rated",
  romance: "Bollywood Romance",
  action: "Bollywood Action",
  comedy: "Bollywood Comedy",
  thriller: "Thrillers & Crime",
  family: "Family Favourites",
  classics: "Golden-Era Classics",
};

type Props = { params: Promise<{ kind: string }> };

async function resolve(kind: string) {
  if (KINDS[kind]) return KINDS[kind];
  const bolly = kind.startsWith("bollywood-") ? BOLLYWOOD[kind.slice("bollywood-".length)] : undefined;
  if (bolly) return { title: bolly, blurb: "Hindi cinema: trailers, cast and where to watch it in India." };
  const m = /^genre-(\d{1,6})$/.exec(kind);
  if (!m) return null;
  const genres = (await serverFetch<Genre[]>("/movies/genres", REVALIDATE.static)) ?? [];
  const genre = genres.find((g) => g.id === Number(m[1]));
  return { title: genre?.name ?? "Genre", blurb: `The best of ${genre?.name.toLowerCase() ?? "this genre"}.` };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const meta = await resolve((await params).kind);
  return { title: meta?.title ?? "Browse" };
}

export default async function BrowsePage({ params }: Props) {
  const { kind } = await params;
  const meta = await resolve(kind);
  if (!meta) notFound();
  const first = await serverFetch<MoviePage>(`/movies/list/${kind}`, kind === "free" ? REVALIDATE.library : REVALIDATE.availability);

  return (
    <div className="min-h-svh px-4 pb-24 pt-32 md:px-12">
      <div className="mx-auto max-w-[1600px]">
        <TitleReveal text={meta.title} className="text-[clamp(2.6rem,6vw,5rem)] text-white" />
        <p className="mt-3 max-w-xl text-white/55">{meta.blurb}</p>
        <div className="mt-10">
          <BrowseGrid kind={kind} initial={first} />
        </div>
      </div>
    </div>
  );
}

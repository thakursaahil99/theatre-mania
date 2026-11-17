import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DetailHero } from "@/components/movie/DetailHero";
import { CastCarousel, VideosRow, WhereToWatch } from "@/components/movie/DetailSections";
import { MovieRow } from "@/components/movie/MovieRow";
import { REVALIDATE, serverFetch } from "@/lib/server-api";
import type { MovieDetail } from "@/lib/types";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }> };
const VALID_KEY = /^[a-z0-9][a-z0-9-]{0,159}$/;

async function load(id: string) {
  return VALID_KEY.test(id) ? serverFetch<MovieDetail>(`/movies/${id}`, REVALIDATE.availability) : null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const movie = await load((await params).id);
  if (!movie) return { title: "Not found" };
  const image = movie.backdrop_path?.startsWith("/") ? `https://image.tmdb.org/t/p/w1280${movie.backdrop_path}` : movie.backdrop_path;
  return {
    title: movie.title,
    description: movie.overview?.slice(0, 160) ?? undefined,
    openGraph: { title: movie.title, description: movie.overview ?? undefined, images: image ? [image] : [] },
  };
}

export default async function MoviePage({ params }: Props) {
  const movie = await load((await params).id);
  if (!movie) notFound();

  return (
    <>
      <DetailHero movie={movie} />
      <div className="relative z-10 space-y-14">
        {movie.cast.length > 0 && <CastCarousel cast={movie.cast} />}
        {movie.videos.length > 1 && <VideosRow videos={movie.videos} />}
        {!movie.availability.streamable && <WhereToWatch providers={movie.watch_providers} title={movie.title} />}
        <MovieRow title={movie.availability.streamable ? "More Free Films" : "More Like This"} items={movie.similar} />
      </div>
    </>
  );
}

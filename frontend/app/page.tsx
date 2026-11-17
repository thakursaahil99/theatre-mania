import { ContinueWatching } from "@/components/home/ContinueWatching";
import { Hero } from "@/components/home/Hero";
import { MovieRow } from "@/components/movie/MovieRow";
import { REVALIDATE, serverFetch } from "@/lib/server-api";
import type { HomeData } from "@/lib/types";

export const dynamic = "force-dynamic"; // data itself is cached (Next data cache + Redis)

export default async function HomePage() {
  const data = await serverFetch<HomeData>("/movies/home", REVALIDATE.availability);
  const rows = data?.rows ?? [];

  return (
    <>
      <Hero items={data?.hero ?? []} />
      <div className="relative z-10 -mt-[10vh] space-y-6 md:space-y-10">
        <ContinueWatching />
        {rows.map((row, i) => (
          <MovieRow key={row.id} title={row.title} items={row.items} href={row.href} priority={i === 0} />
        ))}
        {!data && (
          <p className="px-4 pt-[12vh] text-center text-white/50 md:px-12">
            We couldn&apos;t reach the catalog right now. Please try again in a moment.
          </p>
        )}
      </div>
    </>
  );
}

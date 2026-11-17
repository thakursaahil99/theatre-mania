"use client";

import { LoaderCircle } from "lucide-react";
import { useCallback, useState } from "react";

import { MovieGrid } from "@/components/movie/MovieGrid";
import { api } from "@/lib/api";
import type { MovieCard, MoviePage } from "@/lib/types";

export function BrowseGrid({ kind, initial }: { kind: string; initial: MoviePage | null }) {
  const [movies, setMovies] = useState<MovieCard[]>(initial?.results ?? []);
  const [page, setPage] = useState(initial?.page ?? 1);
  const [total, setTotal] = useState(initial?.total_pages ?? 0);
  const [loading, setLoading] = useState(false);

  const loadMore = useCallback(async () => {
    if (loading || page >= total) return;
    setLoading(true);
    try {
      const data = await api<MoviePage>(`/movies/list/${kind}?page=${page + 1}`);
      setMovies((prev) => {
        const seen = new Set(prev.map((m) => m.id));
        return [...prev, ...data.results.filter((m) => !seen.has(m.id))];
      });
      setPage(data.page);
      setTotal(data.total_pages);
    } finally {
      setLoading(false);
    }
  }, [kind, loading, page, total]);

  if (!movies.length) {
    return (
      <p className="py-24 text-center text-white/50">
        {kind === "free" ? "The free library is being prepared. Check back soon." : "Nothing to show here yet."}
      </p>
    );
  }
  return (
    <>
      <MovieGrid movies={movies} onEndReached={page < total ? loadMore : undefined} />
      {loading && <div className="mt-10 flex justify-center"><LoaderCircle className="size-6 animate-spin text-white/50" /></div>}
    </>
  );
}

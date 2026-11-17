"use client";

import { AnimatePresence, motion } from "framer-motion";
import { LoaderCircle, Search, SlidersHorizontal, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { MovieGrid } from "@/components/movie/MovieGrid";
import { GridSkeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import type { Genre, MovieCard, MoviePage } from "@/lib/types";
import { cn } from "@/lib/utils";

const LANGUAGES: [string, string][] = [
  ["hi", "Hindi"], ["ta", "Tamil"], ["te", "Telugu"], ["ml", "Malayalam"], ["kn", "Kannada"], ["bn", "Bengali"],
  ["mr", "Marathi"], ["pa", "Punjabi"], ["en", "English"], ["ko", "Korean"], ["ja", "Japanese"], ["fr", "French"],
  ["es", "Spanish"], ["de", "German"], ["it", "Italian"], ["zh", "Chinese"],
];
const THIS_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: THIS_YEAR - 1899 }, (_, i) => THIS_YEAR - i);

interface Filters {
  q: string;
  genre: string;
  year: string;
  language: string;
  min_rating: string;
  free_only: boolean;
}

export function SearchView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [filters, setFilters] = useState<Filters>(() => ({
    q: params.get("q") ?? "",
    genre: params.get("genre") ?? "",
    year: params.get("year") ?? "",
    language: params.get("language") ?? "",
    min_rating: params.get("min_rating") ?? "",
    free_only: params.get("free_only") === "true",
  }));
  const [genres, setGenres] = useState<Genre[]>([]);
  const [results, setResults] = useState<MovieCard[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const request = useRef(0);

  const debounced = useDebounced(filters, 300);
  const query = useMemo(() => {
    const qs = new URLSearchParams();
    Object.entries(debounced).forEach(([k, v]) => {
      if (v !== "" && v !== false) qs.set(k, String(v));
    });
    return qs;
  }, [debounced]);

  useEffect(() => {
    api<Genre[]>("/movies/genres").then(setGenres).catch(() => undefined);
    input.current?.focus();
  }, []);

  const fetchPage = useCallback(async (p: number) => {
    const id = ++request.current;
    setLoading(true);
    try {
      const qs = new URLSearchParams(query);
      qs.set("page", String(p));
      const data = await api<MoviePage>(`/search?${qs}`);
      if (id !== request.current) return; // stale response
      setResults((prev) => {
        if (p === 1) return data.results;
        const seen = new Set(prev.map((m) => m.id));
        return [...prev, ...data.results.filter((m) => !seen.has(m.id))];
      });
      setTotalPages(data.total_pages);
      setPage(p);
    } catch {
      if (id === request.current && p === 1) setResults([]);
    } finally {
      if (id === request.current) setLoading(false);
    }
  }, [query]);

  // New filters → page 1, and mirror them in the URL so searches are shareable.
  useEffect(() => {
    void fetchPage(1);
    const qs = query.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [query, fetchPage, router, pathname]);

  const loadMore = useCallback(() => {
    if (!loading && page < totalPages) void fetchPage(page + 1);
  }, [loading, page, totalPages, fetchPage]);

  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters((f) => ({ ...f, [k]: v }));
  const activeCount = [filters.genre, filters.year, filters.language, filters.min_rating].filter(Boolean).length + (filters.free_only ? 1 : 0);
  const heading = filters.q ? `Results for “${debounced.q}”` : activeCount ? "Filtered picks" : "Popular right now";

  return (
    <div className="mx-auto max-w-[1600px]">
      <div className="relative">
        <Search className="pointer-events-none absolute left-5 top-1/2 size-6 -translate-y-1/2 text-white/40" />
        <input
          ref={input}
          type="search"
          value={filters.q}
          onChange={(e) => set("q", e.target.value)}
          placeholder="Search films, e.g. Metropolis"
          aria-label="Search films"
          className="w-full rounded-2xl border border-white/10 bg-white/[0.04] py-5 pl-14 pr-28 text-xl text-white placeholder:text-white/30 transition focus:border-accent/60 focus:bg-white/[0.06] focus:outline-none md:text-2xl"
        />
        <div className="absolute right-3 top-1/2 flex -translate-y-1/2 items-center gap-1">
          {loading && <LoaderCircle className="size-5 animate-spin text-white/50" />}
          {filters.q && (
            <button onClick={() => set("q", "")} aria-label="Clear search" className="grid size-10 place-items-center rounded-full hover:bg-white/10">
              <X className="size-5" />
            </button>
          )}
          <button onClick={() => setShowFilters((s) => !s)} aria-expanded={showFilters} aria-label="Filters"
            className={cn("relative grid size-10 place-items-center rounded-full transition hover:bg-white/10", showFilters && "bg-white/10")}>
            <SlidersHorizontal className="size-5" />
            {activeCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 grid size-4 place-items-center rounded-full bg-accent text-[10px] font-bold">{activeCount}</span>
            )}
          </button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {showFilters && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }} className="overflow-hidden">
            <div className="grid gap-3 pt-4 sm:grid-cols-2 lg:grid-cols-5">
              <select className="field" value={filters.genre} onChange={(e) => set("genre", e.target.value)} aria-label="Genre">
                <option value="">All genres</option>
                {genres.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
              <select className="field" value={filters.year} onChange={(e) => set("year", e.target.value)} aria-label="Release year">
                <option value="">Any year</option>
                {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <select className="field" value={filters.language} onChange={(e) => set("language", e.target.value)} aria-label="Original language">
                <option value="">Any language</option>
                {LANGUAGES.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
              </select>
              <label className="field flex items-center gap-3">
                <span className="shrink-0 text-white/50">Rating ≥ {filters.min_rating || 0}</span>
                <input type="range" min={0} max={9} step={0.5} value={filters.min_rating || 0} className="w-full accent-accent"
                  onChange={(e) => set("min_rating", e.target.value === "0" ? "" : e.target.value)} aria-label="Minimum rating" />
              </label>
              <label className="field flex cursor-pointer items-center justify-between gap-3">
                <span>Free to watch only</span>
                <input type="checkbox" checked={filters.free_only} onChange={(e) => set("free_only", e.target.checked)}
                  className="size-4 accent-accent" />
              </label>
            </div>
            {activeCount > 0 && (
              <button className="mt-3 text-sm text-white/50 underline-offset-4 hover:text-white hover:underline"
                onClick={() => setFilters((f) => ({ ...f, genre: "", year: "", language: "", min_rating: "", free_only: false }))}>
                Clear filters
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <h1 className="mb-6 mt-10 font-display text-3xl tracking-wide md:text-4xl">{heading}</h1>
      {loading && results.length === 0 ? (
        <GridSkeleton />
      ) : results.length === 0 ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="py-24 text-center text-white/50">
          <p className="text-lg">Nothing matched that search.</p>
          <p className="mt-2 text-sm">Try another title, or loosen the filters.</p>
        </motion.div>
      ) : (
        <MovieGrid movies={results} onEndReached={page < totalPages ? loadMore : undefined} />
      )}
      {loading && results.length > 0 && <div className="mt-8 flex justify-center"><LoaderCircle className="size-6 animate-spin text-white/50" /></div>}
    </div>
  );
}

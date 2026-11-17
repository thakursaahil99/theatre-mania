"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function Footer() {
  const pathname = usePathname();
  if (pathname.startsWith("/watch") || pathname.startsWith("/admin")) return null;
  return (
    <footer className="mt-24 border-t border-white/5 px-4 pb-32 pt-12 text-sm text-white/45 md:px-12 md:pb-12">
      <div className="flex flex-col gap-8 md:flex-row md:items-start md:justify-between">
        <div className="max-w-md space-y-3">
          <p className="font-display text-2xl tracking-[0.14em] text-white/80">THEATRE MANIA</p>
          <p className="leading-relaxed">
            We stream only films we have the rights to share: public-domain classics, openly licensed works and our own
            licensed library. Everything else shows official trailers and where to watch it legally. No ads, ever.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-x-12 gap-y-2">
          <Link href="/browse/free" className="hover:text-white">Free to Watch</Link>
          <Link href="/search" className="hover:text-white">Search</Link>
          <Link href="/my-list" className="hover:text-white">My List</Link>
          <Link href="/history" className="hover:text-white">History</Link>
        </div>
      </div>
      <div className="mt-10 flex flex-col gap-3 border-t border-white/5 pt-6 text-xs md:flex-row md:items-center md:justify-between">
        <p>
          Film metadata and images from{" "}
          <a href="https://www.themoviedb.org" target="_blank" rel="noreferrer" className="underline hover:text-white">TMDB</a>.
          This product uses the TMDB API but is not endorsed or certified by TMDB. Streaming availability by JustWatch.
        </p>
        <p>© {new Date().getFullYear()} Theatre Mania</p>
      </div>
    </footer>
  );
}

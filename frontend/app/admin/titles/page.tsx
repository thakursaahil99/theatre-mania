"use client";

import { Plus, Search } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AssetChip, StatusChip, isBusy, licenseSummary } from "@/components/admin/ui";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import type { AdminMovieList } from "@/lib/types";
import { cn, year } from "@/lib/utils";

export default function AdminTitles() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AdminMovieList | null>(null);
  const dq = useDebounced(q, 300);

  useEffect(() => setPage(1), [dq, status]);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      const qs = new URLSearchParams({ page: String(page), page_size: "25" });
      if (dq) qs.set("q", dq);
      if (status) qs.set("status", status);
      try {
        const res = await api<AdminMovieList>(`/admin/movies?${qs}`);
        if (!alive) return;
        setData(res);
        // Keep polling while any transcode is in flight.
        if (res.items.some((m) => m.assets.some((a) => isBusy(a.status)))) timer = setTimeout(load, 4000);
      } catch {
        /* surfaced by empty state */
      }
    };
    void load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [dq, status, page]);

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl tracking-wide">Library</h1>
          <p className="mt-1 text-sm text-white/50">{data ? `${data.total} licensed titles` : "Loading…"}</p>
        </div>
        <Link href="/admin/titles/new" className="btn-brand"><Plus className="size-4" /> Add title</Link>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="relative min-w-60 flex-1">
          <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-white/35" />
          <input className="field pl-11" placeholder="Search titles" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search titles" />
        </div>
        <select className="field w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All statuses</option>
          <option value="published">Published</option>
          <option value="draft">Draft</option>
        </select>
      </div>

      <div className="overflow-hidden rounded-3xl border border-white/[0.06] bg-ink-900/70">
        {!data ? (
          <div className="space-y-2 p-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
        ) : data.items.length === 0 ? (
          <p className="p-10 text-center text-white/50">No titles yet. Add one, or run the public-domain seed script.</p>
        ) : (
          <ul className="divide-y divide-white/5">
            {data.items.map((m) => {
              const asset = m.assets.at(-1);
              const lic = licenseSummary(m.license, m.license_active);
              return (
                <li key={m.id}>
                  <Link href={`/admin/titles/${m.id}`} className="flex items-center gap-4 p-4 transition hover:bg-white/[0.03]">
                    <span className="relative h-16 w-11 shrink-0 overflow-hidden rounded-md bg-ink-800">
                      {m.poster_path && <Image src={m.poster_path} alt="" fill sizes="48px" className="object-cover" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{m.title}</span>
                      <span className="text-xs text-white/40">{year(m.release_date)} {m.tmdb_id ? `· TMDB ${m.tmdb_id}` : "· library only"}</span>
                    </span>
                    <span className={cn("hidden text-xs md:block",
                      lic.tone === "ok" ? "text-white/55" : lic.tone === "warn" ? "text-gold" : "text-danger")}>{lic.text}</span>
                    <span className="hidden w-36 justify-end sm:flex">
                      {asset ? <AssetChip status={asset.status} progress={asset.progress} /> : <span className="text-xs text-white/35">No video</span>}
                    </span>
                    <StatusChip status={m.status} />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button className="btn-ghost px-4 py-2" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <span className="text-white/50">Page {page} of {pages}</span>
          <button className="btn-ghost px-4 py-2" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}

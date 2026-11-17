"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import { DailyChart } from "@/components/admin/DailyChart";
import { Section } from "@/components/admin/ui";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { Analytics } from "@/lib/types";
import { cn } from "@/lib/utils";

const RANGES = [7, 30, 90];

export default function AdminDashboard() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Analytics | null>(null);

  useEffect(() => {
    setData(null);
    api<Analytics>(`/admin/analytics?days=${days}`).then(setData).catch(() => undefined);
  }, [days]);

  const stats: [string, string | number, string?][] = data
    ? [
        ["Views", data.views.toLocaleString(), `last ${days} days`],
        ["Watch time", `${data.watch_hours.toLocaleString()} h`, `last ${days} days`],
        ["Unique viewers", data.unique_viewers.toLocaleString(), "profiles"],
        ["Streamable now", `${data.published} / ${data.library_size}`, "published / library"],
        ["Licenses expiring", data.expiring_soon, "next 30 days"],
        ["Jobs running", data.processing_jobs, "transcode queue"],
      ]
    : [];

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl tracking-wide">Dashboard</h1>
          <p className="mt-1 text-sm text-white/50">How the library is performing.</p>
        </div>
        <div className="flex rounded-full border border-white/10 p-1" role="group" aria-label="Date range">
          {RANGES.map((d) => (
            <button key={d} onClick={() => setDays(d)} aria-pressed={days === d}
              className={cn("rounded-full px-4 py-1.5 text-sm transition", days === d ? "bg-white text-ink-950" : "text-white/60 hover:text-white")}>
              {d}d
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        {data
          ? stats.map(([label, value, hint]) => (
              <div key={label} className="rounded-2xl border border-white/[0.06] bg-ink-900/70 p-5">
                <p className="text-xs uppercase tracking-[0.16em] text-white/45">{label}</p>
                <p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p>
                {hint && <p className="mt-1 text-xs text-white/35">{hint}</p>}
              </div>
            ))
          : Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
      </div>

      <Section title="Views per day" description="Playback starts (token renewals are not counted twice).">
        {data ? <DailyChart data={data.daily} /> : <Skeleton className="h-56" />}
      </Section>

      <Section title="Top titles" description={`By watch time, last ${days} days.`}>
        {!data ? (
          <Skeleton className="h-40" />
        ) : data.top_movies.length === 0 ? (
          <p className="text-sm text-white/50">No plays yet in this period.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-[0.14em] text-white/40">
                <th className="pb-3 font-medium">Title</th>
                <th className="pb-3 text-right font-medium">Views</th>
                <th className="pb-3 text-right font-medium">Watch time</th>
              </tr>
            </thead>
            <tbody>
              {data.top_movies.map((m, i) => (
                <tr key={m.movie_id} className="border-t border-white/5">
                  <td className="py-3">
                    <span className="flex items-center gap-3">
                      <span className="w-5 text-white/35 tabular-nums">{i + 1}</span>
                      <span className="relative h-12 w-8 shrink-0 overflow-hidden rounded bg-ink-800">
                        {m.poster_path && <Image src={m.poster_path} alt="" fill sizes="40px" className="object-cover" />}
                      </span>
                      {m.title}
                    </span>
                  </td>
                  <td className="py-3 text-right tabular-nums">{m.views.toLocaleString()}</td>
                  <td className="py-3 text-right tabular-nums">{(m.watch_minutes / 60).toFixed(1)} h</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}

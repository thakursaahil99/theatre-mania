"use client";

import { useMemo, useState } from "react";

import type { Analytics } from "@/lib/types";

/**
 * Single-series bar chart (views per day). One hue (validated against the dark surface),
 * 4px rounded data-ends on the baseline, 2px gaps, recessive grid, per-bar hover tooltip
 * with hit targets wider than the bar, and a visually-hidden table for screen readers.
 */
export function DailyChart({ data }: { data: Analytics["daily"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 800;
  const H = 220;
  const pad = { top: 12, right: 8, bottom: 26, left: 36 };
  const innerW = W - pad.left - pad.right;
  const innerH = H - pad.top - pad.bottom;

  const { max, ticks } = useMemo(() => {
    const raw = Math.max(1, ...data.map((d) => d.views));
    const step = niceStep(raw / 4);
    const top = Math.ceil(raw / step) * step;
    return { max: top, ticks: Array.from({ length: top / step + 1 }, (_, i) => i * step) };
  }, [data]);

  const slot = innerW / Math.max(1, data.length);
  const barW = Math.max(2, Math.min(28, slot - 2)); // ≥2px surface gap between bars
  const y = (v: number) => pad.top + innerH - (v / max) * innerH;
  const labelEvery = Math.ceil(data.length / 8);
  const h = hover !== null ? data[hover] : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-56 w-full" role="img" aria-label="Views per day" onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={W - pad.right} y1={y(t)} y2={y(t)} stroke="rgb(255 255 255 / 0.06)" strokeWidth={1} />
            <text x={pad.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-white/40 text-[11px] tabular-nums">{t}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = pad.left + i * slot + (slot - barW) / 2;
          const top = y(d.views);
          const height = pad.top + innerH - top;
          const r = Math.min(4, barW / 2, height);
          return (
            <g key={d.date}>
              {d.views > 0 && (
                <path
                  d={`M${x},${top + height} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${top + height} Z`}
                  fill="#7c5cff"
                  opacity={hover === null || hover === i ? 1 : 0.45}
                />
              )}
              {/* Generous invisible hit target */}
              <rect x={pad.left + i * slot} y={pad.top} width={slot} height={innerH} fill="transparent"
                onMouseEnter={() => setHover(i)} />
              {i % labelEvery === 0 && (
                <text x={x + barW / 2} y={H - 8} textAnchor="middle" className="fill-white/40 text-[11px]">
                  {new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </text>
              )}
            </g>
          );
        })}
        <line x1={pad.left} x2={W - pad.right} y1={pad.top + innerH} y2={pad.top + innerH} stroke="rgb(255 255 255 / 0.15)" />
      </svg>
      {h && hover !== null && (
        <div className="pointer-events-none absolute top-0 -translate-x-1/2 rounded-lg border border-white/10 bg-ink-800 px-3 py-2 text-xs shadow-xl"
          style={{ left: `${((pad.left + hover * slot + slot / 2) / W) * 100}%` }}>
          <p className="text-white/50">{new Date(h.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</p>
          <p className="mt-1 font-semibold text-white">{h.views} views</p>
          <p className="text-white/70">{h.watch_minutes} min watched</p>
        </div>
      )}
      <table className="sr-only">
        <caption>Views and watch minutes per day</caption>
        <thead><tr><th>Date</th><th>Views</th><th>Watch minutes</th></tr></thead>
        <tbody>{data.map((d) => <tr key={d.date}><td>{d.date}</td><td>{d.views}</td><td>{d.watch_minutes}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function niceStep(raw: number): number {
  if (raw <= 1) return 1;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const n = raw / pow;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
}

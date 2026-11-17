import { clsx, type ClassValue } from "clsx";

export const cn = (...inputs: ClassValue[]) => clsx(inputs);

export const year = (date: string | null | undefined) => (date ? date.slice(0, 4) : "");

export function runtime(minutes: number | null | undefined): string {
  if (!minutes) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h}h ${m.toString().padStart(2, "0")}m` : `${m}m`;
}

export function clock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const s = Math.floor(seconds % 60);
  const m = Math.floor((seconds / 60) % 60);
  const h = Math.floor(seconds / 3600);
  const mm = h ? m.toString().padStart(2, "0") : String(m);
  return `${h ? `${h}:` : ""}${mm}:${s.toString().padStart(2, "0")}`;
}

/** "1:23:45" | "83:45" | "45" → seconds (admin intro markers). */
export function parseClock(value: string): number | null {
  const parts = value.trim().split(":").map(Number);
  if (!value.trim() || parts.some((p) => Number.isNaN(p) || p < 0)) return null;
  return parts.reduce((acc, p) => acc * 60 + p, 0);
}

export const rating = (v: number | null | undefined) => (v ? v.toFixed(1) : "—");

export const LICENSE_LABEL: Record<string, string> = {
  public_domain: "Public Domain",
  creative_commons: "Creative Commons",
  owned: "Theatre Mania Original",
  licensed: "Licensed",
};

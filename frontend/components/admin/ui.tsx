"use client";

import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { AssetStatus, License, LicenseType } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Section({ title, description, children, actions }: {
  title: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-white/[0.06] bg-ink-900/70 p-5 md:p-7">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          {description && <p className="mt-1 text-sm text-white/50">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Label({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.16em] text-white/45">
      {children} {hint && <span className="normal-case tracking-normal text-white/30">· {hint}</span>}
    </span>
  );
}

const ASSET_STYLES: Record<AssetStatus, { label: string; cls: string }> = {
  pending_upload: { label: "Awaiting upload", cls: "text-white/60 border-white/15" },
  queued: { label: "Queued", cls: "text-gold border-gold/30 bg-gold/10" },
  downloading: { label: "Downloading", cls: "text-accent border-accent/30 bg-accent/10" },
  processing: { label: "Transcoding", cls: "text-accent border-accent/30 bg-accent/10" },
  ready: { label: "Ready", cls: "text-success border-success/30 bg-success/10" },
  failed: { label: "Failed", cls: "text-danger border-danger/30 bg-danger/10" },
};

export const isBusy = (s: AssetStatus) => s === "queued" || s === "downloading" || s === "processing";

export function AssetChip({ status, progress }: { status: AssetStatus; progress?: number }) {
  const s = ASSET_STYLES[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium", s.cls)}>
      {isBusy(status) ? <LoaderCircle className="size-3 animate-spin" /> : status === "ready" ? <CircleCheck className="size-3" />
        : status === "failed" ? <CircleAlert className="size-3" /> : null}
      {s.label}
      {isBusy(status) && progress !== undefined && progress > 0 ? ` ${progress}%` : ""}
    </span>
  );
}

export function StatusChip({ status }: { status: "draft" | "published" | "archived" }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
      status === "published" ? "border-success/30 bg-success/10 text-success" : "border-white/15 text-white/60")}>
      <span className={cn("size-1.5 rounded-full", status === "published" ? "bg-success" : "bg-white/40")} />
      {status}
    </span>
  );
}

export const LICENSE_TYPES: { value: LicenseType; label: string }[] = [
  { value: "public_domain", label: "Public domain" },
  { value: "creative_commons", label: "Creative Commons" },
  { value: "owned", label: "Owned / original" },
  { value: "licensed", label: "Licensed (third party)" },
];

export function licenseSummary(lic: License | null, active: boolean): { text: string; tone: "ok" | "warn" | "bad" } {
  if (!lic) return { text: "No license", tone: "bad" };
  const type = LICENSE_TYPES.find((t) => t.value === lic.license_type)?.label ?? lic.license_type;
  if (!active) return { text: `${type} · inactive`, tone: "bad" };
  if (lic.expires_at) {
    const days = Math.ceil((new Date(lic.expires_at).getTime() - Date.now()) / 86400000);
    return { text: `${type} · expires in ${days}d`, tone: days <= 30 ? "warn" : "ok" };
  }
  return { text: `${type} · perpetual`, tone: "ok" };
}

export function formatBytes(n: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

"use client";

import { CircleCheck, CircleX, ExternalLink, LoaderCircle, RefreshCw } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";

import { AssetPanel } from "@/components/admin/AssetPanel";
import { LicenseForm, emptyLicense, licensePayload } from "@/components/admin/LicenseForm";
import { Label, Section, StatusChip, isBusy, licenseSummary } from "@/components/admin/ui";
import { ApiError, api } from "@/lib/api";
import type { AdminMovie } from "@/lib/types";
import { cn, year } from "@/lib/utils";

export default function EditTitle({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [movie, setMovie] = useState<AdminMovie | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMovie(await api<AdminMovie>(`/admin/movies/${id}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Could not load title");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll while any transcode is running.
  const processing = movie?.assets.some((a) => isBusy(a.status));
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [processing, load]);

  const action = async (name: string, fn: () => Promise<AdminMovie | void>) => {
    setBusy(name);
    setError(null);
    try {
      const res = await fn();
      if (res) setMovie(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Action failed");
    } finally {
      setBusy(null);
    }
  };

  if (!movie) {
    return error ? <p className="text-danger">{error}</p> : <LoaderCircle className="size-8 animate-spin text-white/50" />;
  }

  const hasReady = movie.assets.some((a) => a.status === "ready");
  const canPublish = movie.license_active && hasReady;
  const lic = licenseSummary(movie.license, movie.license_active);
  const publicKey = movie.tmdb_id ? String(movie.tmdb_id) : movie.slug;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-start gap-6">
        <span className="relative aspect-[2/3] w-28 shrink-0 overflow-hidden rounded-xl bg-ink-800 ring-1 ring-white/10">
          {movie.poster_path && <Image src={movie.poster_path} alt="" fill sizes="120px" className="object-cover" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <StatusChip status={movie.status} />
            <span className="text-xs text-white/40">{movie.tmdb_id ? `TMDB ${movie.tmdb_id}` : "Library only"} · /{movie.slug}</span>
          </div>
          <h1 className="mt-2 font-display text-4xl tracking-wide">{movie.title} <span className="text-white/35">{year(movie.release_date)}</span></h1>
          <ul className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <Check ok={movie.license_active} label={lic.text} />
            <Check ok={hasReady} label={hasReady ? "Video ready" : "No ready video"} />
          </ul>
          <div className="mt-5 flex flex-wrap gap-3">
            {movie.status === "published" ? (
              <button className="btn-ghost" disabled={!!busy}
                onClick={() => action("unpublish", () => api(`/admin/movies/${id}/unpublish`, { method: "POST" }))}>Unpublish</button>
            ) : (
              <button className="btn-brand" disabled={!canPublish || !!busy} title={canPublish ? "" : "Needs an active license and a ready video"}
                onClick={() => action("publish", () => api(`/admin/movies/${id}/publish`, { method: "POST" }))}>
                {busy === "publish" && <LoaderCircle className="size-4 animate-spin" />} Publish
              </button>
            )}
            {movie.tmdb_id && (
              <button className="btn-ghost" disabled={!!busy}
                onClick={() => action("refresh", () => api(`/admin/movies/${id}/refresh-metadata`, { method: "POST" }))}>
                <RefreshCw className={cn("size-4", busy === "refresh" && "animate-spin")} /> Refresh TMDB
              </button>
            )}
            <Link href={`/movie/${publicKey}`} target="_blank" className="btn-ghost"><ExternalLink className="size-4" /> View</Link>
          </div>
        </div>
      </div>

      {error && <p role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>}

      <AssetPanel movie={movie} onChange={load} />
      <LicensePanel movie={movie} onSaved={setMovie} />
      <MetadataPanel movie={movie} onSaved={setMovie} />

      <Section title="Danger zone" description="Deletes the title, its licenses, video renditions and viewing history.">
        <button className="btn border border-danger/40 text-danger hover:bg-danger/10" disabled={!!busy}
          onClick={() => confirm(`Permanently delete “${movie.title}” and its media?`) &&
            action("delete", async () => { await api(`/admin/movies/${id}`, { method: "DELETE" }); router.push("/admin/titles"); })}>
          Delete title
        </button>
      </Section>
    </div>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className={cn("flex items-center gap-1.5", ok ? "text-success" : "text-white/50")}>
      {ok ? <CircleCheck className="size-4" /> : <CircleX className="size-4" />} {label}
    </li>
  );
}

function LicensePanel({ movie, onSaved }: { movie: AdminMovie; onSaved: (m: AdminMovie) => void }) {
  const lic = movie.license;
  const [draft, setDraft] = useState(() => lic ? {
    license_type: lic.license_type,
    licensor: lic.licensor ?? "",
    source_url: lic.source_url ?? "",
    territories: lic.territories.join(", "),
    starts_at: lic.starts_at?.slice(0, 10) ?? "",
    expires_at: lic.expires_at?.slice(0, 10) ?? "",
    notes: lic.notes ?? "",
  } : emptyLicense());
  const [msg, setMsg] = useState<string | null>(null);

  const save = async () => {
    setMsg(null);
    try {
      onSaved(await api<AdminMovie>(`/admin/movies/${movie.id}/license`, { method: "PUT", json: licensePayload(draft) }));
      setMsg("New license window saved. Previous windows are kept for the audit trail.");
    } catch (e) {
      setMsg(e instanceof ApiError ? e.detail : "Could not save");
    }
  };

  return (
    <Section title="License" description="Saving creates a new license window; streaming stops automatically when it expires.">
      <LicenseForm value={draft} onChange={setDraft} />
      <div className="mt-5 flex items-center gap-4">
        <button className="btn-ghost" onClick={save}>Save license</button>
        {msg && <p className="text-sm text-white/60">{msg}</p>}
      </div>
    </Section>
  );
}

function MetadataPanel({ movie, onSaved }: { movie: AdminMovie; onSaved: (m: AdminMovie) => void }) {
  const [form, setForm] = useState({
    title: movie.title,
    tagline: movie.tagline ?? "",
    overview: movie.overview ?? "",
    trailer_key: movie.trailer_key ?? "",
    poster_path: movie.poster_path ?? "",
    backdrop_path: movie.backdrop_path ?? "",
  });
  const [msg, setMsg] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  const save = async () => {
    setMsg(null);
    try {
      const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === "" && k !== "title" ? null : v]));
      onSaved(await api<AdminMovie>(`/admin/movies/${movie.id}`, { method: "PATCH", json: body }));
      setMsg("Saved");
    } catch (e) {
      setMsg(e instanceof ApiError ? e.detail : "Could not save");
    }
  };

  return (
    <Section title="Metadata overrides" description="Edits apply on top of TMDB data (a TMDB refresh will overwrite them).">
      <div className="grid gap-4 md:grid-cols-2">
        <label><Label>Title</Label><input className="field" value={form.title} onChange={set("title")} /></label>
        <label><Label>Tagline</Label><input className="field" value={form.tagline} onChange={set("tagline")} /></label>
        <label className="md:col-span-2"><Label>Overview</Label><textarea className="field min-h-24" value={form.overview} onChange={set("overview")} /></label>
        <label><Label hint="YouTube video id">Trailer key</Label><input className="field" value={form.trailer_key} onChange={set("trailer_key")} /></label>
        <label><Label hint="TMDB path or https URL">Poster</Label><input className="field" value={form.poster_path} onChange={set("poster_path")} /></label>
        <label className="md:col-span-2"><Label hint="TMDB path or https URL">Backdrop</Label><input className="field" value={form.backdrop_path} onChange={set("backdrop_path")} /></label>
      </div>
      <div className="mt-5 flex items-center gap-4">
        <button className="btn-ghost" onClick={save}>Save metadata</button>
        {msg && <p className="text-sm text-white/60">{msg}</p>}
      </div>
    </Section>
  );
}

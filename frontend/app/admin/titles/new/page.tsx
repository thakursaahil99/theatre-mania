"use client";

import { AnimatePresence, motion } from "framer-motion";
import { LoaderCircle } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { LicenseForm, emptyLicense, licensePayload } from "@/components/admin/LicenseForm";
import { Label, Section } from "@/components/admin/ui";
import { ApiError, api } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import type { AdminMovie } from "@/lib/types";
import { cn, year } from "@/lib/utils";

interface TmdbPreview {
  tmdb_id: number;
  title: string;
  overview: string | null;
  release_date: string | null;
  poster_path: string | null;
  runtime: number | null;
}

export default function NewTitle() {
  const router = useRouter();
  const [mode, setMode] = useState<"tmdb" | "manual">("tmdb");
  const [tmdbId, setTmdbId] = useState("");
  const [preview, setPreview] = useState<TmdbPreview | null>(null);
  const [lookup, setLookup] = useState<"idle" | "loading" | "missing">("idle");
  const [manual, setManual] = useState({ title: "", overview: "", release_date: "" });
  const [license, setLicense] = useState(emptyLicense);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const debouncedId = useDebounced(tmdbId, 500);

  useEffect(() => {
    setPreview(null);
    if (mode !== "tmdb" || !/^\d+$/.test(debouncedId)) return setLookup("idle");
    setLookup("loading");
    api<TmdbPreview>(`/admin/tmdb/${debouncedId}`)
      .then((p) => { setPreview(p); setLookup("idle"); })
      .catch(() => setLookup("missing"));
  }, [debouncedId, mode]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = mode === "tmdb"
        ? { tmdb_id: Number(tmdbId), license: licensePayload(license) }
        : { title: manual.title, overview: manual.overview || null, release_date: manual.release_date || null, license: licensePayload(license) };
      const movie = await api<AdminMovie>("/admin/movies", { method: "POST", json: body });
      router.push(`/admin/titles/${movie.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not create title");
      setBusy(false);
    }
  };

  const ready = mode === "tmdb" ? Boolean(preview) : Boolean(manual.title.trim());

  return (
    <form onSubmit={submit} className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="font-display text-4xl tracking-wide">Add a title</h1>
        <p className="mt-1 text-sm text-white/50">Only add films you hold the rights to stream. Everything else is shown as metadata + trailer automatically.</p>
      </div>

      <Section title="Metadata" description="Pull everything from TMDB by ID, or enter it manually for originals.">
        <div className="mb-5 inline-flex rounded-full border border-white/10 p-1">
          {(["tmdb", "manual"] as const).map((m) => (
            <button key={m} type="button" onClick={() => setMode(m)}
              className={cn("rounded-full px-4 py-1.5 text-sm transition", mode === m ? "bg-white text-ink-950" : "text-white/60")}>
              {m === "tmdb" ? "From TMDB" : "Manual"}
            </button>
          ))}
        </div>

        {mode === "tmdb" ? (
          <div className="space-y-4">
            <label className="block max-w-xs">
              <Label hint="the number in themoviedb.org/movie/<id>">TMDB ID</Label>
              <input className="field" inputMode="numeric" value={tmdbId} onChange={(e) => setTmdbId(e.target.value.replace(/\D/g, ""))}
                placeholder="10331" />
            </label>
            <AnimatePresence mode="wait">
              {lookup === "loading" && <motion.p key="l" className="flex items-center gap-2 text-sm text-white/50"><LoaderCircle className="size-4 animate-spin" /> Looking up…</motion.p>}
              {lookup === "missing" && <motion.p key="m" className="text-sm text-danger">No TMDB title with that ID.</motion.p>}
              {preview && (
                <motion.div key="p" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                  className="flex gap-5 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <span className="relative aspect-[2/3] w-24 shrink-0 overflow-hidden rounded-lg bg-ink-800">
                    {preview.poster_path && <Image src={preview.poster_path} alt="" fill sizes="100px" className="object-cover" />}
                  </span>
                  <div>
                    <p className="text-lg font-semibold">{preview.title} <span className="text-white/45">({year(preview.release_date)})</span></p>
                    {preview.runtime ? <p className="text-sm text-white/45">{preview.runtime} min</p> : null}
                    <p className="mt-2 line-clamp-4 text-sm text-white/65">{preview.overview}</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            <label className="md:col-span-2"><Label>Title</Label>
              <input className="field" value={manual.title} onChange={(e) => setManual({ ...manual, title: e.target.value })} required /></label>
            <label><Label>Release date</Label>
              <input className="field" type="date" value={manual.release_date} onChange={(e) => setManual({ ...manual, release_date: e.target.value })} /></label>
            <label className="md:col-span-2"><Label>Overview</Label>
              <textarea className="field min-h-24" value={manual.overview} onChange={(e) => setManual({ ...manual, overview: e.target.value })} /></label>
          </div>
        )}
      </Section>

      <Section title="Streaming rights" description="A title is only streamable while its license window is active.">
        <LicenseForm value={license} onChange={setLicense} />
      </Section>

      {error && <p role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>}
      <div className="flex justify-end">
        <button type="submit" disabled={!ready || busy} className="btn-brand">
          {busy && <LoaderCircle className="size-4 animate-spin" />} Create draft
        </button>
      </div>
    </form>
  );
}

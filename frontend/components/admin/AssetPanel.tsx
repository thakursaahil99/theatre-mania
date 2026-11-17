"use client";

import { motion } from "framer-motion";
import { CloudUpload, Link2, LoaderCircle, RefreshCw, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { AssetChip, Label, Section, formatBytes, isBusy } from "@/components/admin/ui";
import { ApiError, api } from "@/lib/api";
import type { AdminMovie, Asset } from "@/lib/types";
import { clock, cn, parseClock } from "@/lib/utils";

/** Upload a mezzanine file straight to object storage (presigned PUT) or import from archive.org. */
export function AssetPanel({ movie, onChange }: { movie: AdminMovie; onChange: () => Promise<void> }) {
  const [upload, setUpload] = useState<{ name: string; size: number; pct: number } | null>(null);
  const [importUrl, setImportUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const startUpload = async (file: File) => {
    setError(null);
    if (!file.type.startsWith("video/")) return setError("Please choose a video file.");
    setUpload({ name: file.name, size: file.size, pct: 0 });
    try {
      const target = await api<{ asset_id: string; upload_url: string; headers: Record<string, string> }>(
        `/admin/movies/${movie.id}/assets/upload-url`,
        { method: "POST", json: { filename: file.name, content_type: file.type, size_bytes: file.size } },
      );
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", target.upload_url);
        Object.entries(target.headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
        xhr.upload.onprogress = (e) => e.lengthComputable && setUpload((u) => u && { ...u, pct: Math.round((e.loaded / e.total) * 100) });
        xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`Storage rejected the upload (${xhr.status})`)));
        xhr.onerror = () => reject(new Error("Upload failed. Check the bucket's CORS settings."));
        xhr.send(file);
      });
      await api(`/admin/assets/${target.asset_id}/complete`, { method: "POST" });
      await onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUpload(null);
    }
  };

  const startImport = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api(`/admin/movies/${movie.id}/assets/import`, { method: "POST", json: { source_url: importUrl } });
      setImportUrl("");
      await onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Import failed");
    }
  };

  return (
    <Section title="Video" description="Each upload is transcoded by FFmpeg into adaptive HLS (360p → 1080p, never upscaled).">
      <div className="grid gap-4 lg:grid-cols-2">
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) void startUpload(f); }}
          disabled={!!upload}
          className={cn("relative flex min-h-40 flex-col items-center justify-center gap-2 overflow-hidden rounded-2xl border-2 border-dashed p-6 text-center transition",
            dragging ? "border-accent bg-accent/10" : "border-white/15 hover:border-white/35 hover:bg-white/[0.02]")}
        >
          {upload ? (
            <>
              <LoaderCircle className="size-7 animate-spin text-accent" />
              <p className="text-sm">{upload.name}</p>
              <p className="text-xs text-white/45">{formatBytes(upload.size)} · {upload.pct}%</p>
              <motion.span className="absolute inset-x-0 bottom-0 h-1 brand-gradient" style={{ width: `${upload.pct}%` }} />
            </>
          ) : (
            <>
              <CloudUpload className="size-8 text-white/50" />
              <p className="text-sm font-medium">Drop a video or click to upload</p>
              <p className="text-xs text-white/40">MP4 / MOV / MKV up to 5 GB, sent directly to storage</p>
            </>
          )}
          <input ref={fileInput} type="file" accept="video/*" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void startUpload(f); e.target.value = ""; }} />
        </button>

        <form onSubmit={startImport} className="flex flex-col justify-center gap-3 rounded-2xl border border-white/10 p-6">
          <Label hint="allow-listed hosts only">Import from Internet Archive</Label>
          <div className="flex gap-2">
            <input className="field" type="url" required value={importUrl} onChange={(e) => setImportUrl(e.target.value)}
              placeholder="https://archive.org/download/<item>/<file>.mp4" />
            <button type="submit" className="btn-ghost shrink-0 px-4"><Link2 className="size-4" /> Import</button>
          </div>
          <p className="text-xs text-white/40">The worker downloads and transcodes in the background.</p>
        </form>
      </div>

      {error && <p role="alert" className="mt-4 text-sm text-danger">{error}</p>}

      <div className="mt-6 space-y-4">
        {[...movie.assets].reverse().map((a) => <AssetCard key={a.id} asset={a} onChange={onChange} />)}
      </div>
    </Section>
  );
}

function AssetCard({ asset, onChange }: { asset: Asset; onChange: () => Promise<void> }) {
  const [intro, setIntro] = useState({
    start: asset.intro_start_sec !== null ? clock(asset.intro_start_sec) : "",
    end: asset.intro_end_sec !== null ? clock(asset.intro_end_sec) : "",
    credits: asset.credits_start_sec !== null ? clock(asset.credits_start_sec) : "",
  });
  const [msg, setMsg] = useState<string | null>(null);
  const subForm = useRef<HTMLFormElement>(null);

  const saveMarkers = async () => {
    setMsg(null);
    try {
      await api(`/admin/assets/${asset.id}`, {
        method: "PATCH",
        json: { intro_start_sec: parseClock(intro.start), intro_end_sec: parseClock(intro.end), credits_start_sec: parseClock(intro.credits) },
      });
      setMsg("Markers saved");
      await onChange();
    } catch (e) {
      setMsg(e instanceof ApiError ? e.detail : "Could not save");
    }
  };

  const uploadSub = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setMsg(null);
    try {
      await api(`/admin/assets/${asset.id}/subtitles`, { method: "POST", body: new FormData(e.currentTarget) });
      subForm.current?.reset();
      await onChange();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.detail : "Subtitle upload failed");
    }
  };

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="flex flex-wrap items-center gap-3">
        <AssetChip status={asset.status} progress={asset.progress} />
        <span className="text-xs text-white/40">Added {new Date(asset.created_at).toLocaleString()}</span>
        {asset.duration_seconds && <span className="text-xs text-white/55">{clock(asset.duration_seconds)}</span>}
        {asset.width && <span className="text-xs text-white/55">source {asset.width}×{asset.height}</span>}
        {(asset.status === "failed" || asset.status === "ready") && (
          <button className="ml-auto inline-flex items-center gap-1.5 text-xs text-white/60 hover:text-white"
            onClick={async () => { await api(`/admin/assets/${asset.id}/retry`, { method: "POST" }); await onChange(); }}>
            <RefreshCw className="size-3.5" /> {asset.status === "failed" ? "Retry" : "Re-transcode"}
          </button>
        )}
      </div>

      {isBusy(asset.status) && (
        <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10">
          <motion.div className="h-full brand-gradient" animate={{ width: `${Math.max(asset.progress, 3)}%` }} transition={{ duration: 0.6 }} />
        </div>
      )}
      {asset.error && <pre className="mt-4 max-h-32 overflow-auto rounded-xl bg-danger/10 p-3 text-xs text-danger whitespace-pre-wrap">{asset.error}</pre>}
      {asset.renditions && (
        <div className="mt-4 flex flex-wrap gap-2">
          {asset.renditions.map((r) => (
            <span key={r.name} className="chip">{r.name}{r.bandwidth ? ` · ${(r.bandwidth / 1e6).toFixed(1)} Mbps` : ""}</span>
          ))}
        </div>
      )}

      {asset.status === "ready" && (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <div>
            <Label hint="mm:ss or h:mm:ss">Skip-intro markers</Label>
            <div className="grid grid-cols-3 gap-2">
              <input className="field" placeholder="Intro start" value={intro.start} onChange={(e) => setIntro({ ...intro, start: e.target.value })} aria-label="Intro start" />
              <input className="field" placeholder="Intro end" value={intro.end} onChange={(e) => setIntro({ ...intro, end: e.target.value })} aria-label="Intro end" />
              <input className="field" placeholder="Credits" value={intro.credits} onChange={(e) => setIntro({ ...intro, credits: e.target.value })} aria-label="Credits start" />
            </div>
            <button type="button" onClick={saveMarkers} className="btn-ghost mt-3 px-4 py-2 text-xs">Save markers</button>
          </div>

          <div>
            <Label>Subtitles (.vtt or .srt)</Label>
            <ul className="mb-3 space-y-1.5">
              {asset.subtitles.map((s) => (
                <li key={s.id} className="flex items-center gap-2 text-sm">
                  <span className="chip">{s.language}</span> {s.label} {s.is_default && <span className="text-xs text-white/40">default</span>}
                  <button className="ml-auto text-white/40 hover:text-danger" aria-label={`Delete ${s.label} subtitles`}
                    onClick={async () => { await api(`/admin/subtitles/${s.id}`, { method: "DELETE" }); await onChange(); }}>
                    <Trash2 className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
            <form ref={subForm} onSubmit={uploadSub} className="grid grid-cols-2 gap-2">
              <input name="file" type="file" accept=".vtt,.srt,text/vtt" required className="col-span-2 text-xs text-white/60 file:mr-3 file:rounded-full file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-white" />
              <input name="language" className="field" placeholder="en" required pattern="[a-z]{2}(-[A-Z]{2})?" aria-label="Language code" />
              <input name="label" className="field" placeholder="English" required aria-label="Label" />
              <label className="flex items-center gap-2 text-xs text-white/60">
                <input type="checkbox" name="is_default" value="true" className="accent-accent" /> Default track
              </label>
              <button type="submit" className="btn-ghost px-4 py-2 text-xs">Add subtitles</button>
            </form>
          </div>
        </div>
      )}
      {msg && <p className="mt-3 text-xs text-white/60">{msg}</p>}
    </div>
  );
}

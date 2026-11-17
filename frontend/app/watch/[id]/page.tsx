"use client";

import { LoaderCircle, Lock } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { VideoPlayer } from "@/components/player/VideoPlayer";
import { hasInAppHistory, useLenis } from "@/components/providers/SmoothScroll";
import { ApiError, api } from "@/lib/api";
import type { Playback } from "@/lib/types";

export default function WatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const lenis = useLenis();
  const [playback, setPlayback] = useState<Playback | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const session = useRef<string | null>(null);

  const start = useCallback(async () => {
    try {
      const qs = session.current ? `?session_id=${session.current}` : "";
      const p = await api<Playback>(`/playback/${encodeURIComponent(id)}/start${qs}`, { method: "POST" });
      session.current = p.session_id;
      setPlayback(p);
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return router.replace(`/login?next=/watch/${id}`);
      setError({ status: e instanceof ApiError ? e.status : 0, message: e instanceof Error ? e.message : "Something went wrong" });
    }
  }, [id, router]);

  useEffect(() => {
    void start();
  }, [start]);

  useEffect(() => {
    lenis.current?.stop();
    document.documentElement.style.overflow = "hidden";
    return () => {
      lenis.current?.start();
      document.documentElement.style.overflow = "";
    };
  }, [lenis]);

  // Deep links (shared URL, new tab) go to the film's page instead of leaving the site.
  const back = useCallback(() => {
    if (hasInAppHistory()) router.back();
    else router.push(`/movie/${id}`);
  }, [router, id]);

  if (error) {
    return (
      <div className="fixed inset-0 z-50 grid place-items-center bg-ink-950 p-6 text-center">
        <div className="max-w-md">
          <span className="mx-auto grid size-16 place-items-center rounded-full bg-white/5"><Lock className="size-7 text-white/60" /></span>
          <h1 className="mt-6 text-2xl font-semibold">{error.status === 403 ? "Not available to stream" : "Playback error"}</h1>
          <p className="mt-3 text-white/60">
            {error.status === 403
              ? "We only stream films we have the rights to share. You can still watch the trailer and find where it's available."
              : error.message}
          </p>
          <Link href={`/movie/${id}`} className="btn-primary mt-8">Back to details</Link>
        </div>
      </div>
    );
  }

  if (!playback) {
    return (
      <div className="fixed inset-0 z-50 grid place-items-center bg-black" aria-busy="true">
        <LoaderCircle className="size-12 animate-spin text-white/70" />
      </div>
    );
  }

  return <VideoPlayer playback={playback} onRenew={start} onBack={back} />;
}

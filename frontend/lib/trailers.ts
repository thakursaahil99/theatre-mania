"use client";

import { api } from "@/lib/api";
import type { Video } from "@/lib/types";

const cache = new Map<string, Promise<Video | null>>();

/** Trailer lookup for hover previews, de-duplicated and memoised per session. */
export function getTrailer(movieId: string): Promise<Video | null> {
  let p = cache.get(movieId);
  if (!p) {
    p = api<{ trailer: Video | null }>(`/movies/${movieId}/trailer`)
      .then((r) => r.trailer)
      .catch(() => null);
    cache.set(movieId, p);
  }
  return p;
}

export function youtubeEmbed(key: string, opts: { muted?: boolean; controls?: boolean; loop?: boolean; start?: number } = {}) {
  const { muted = true, controls = false, loop = true, start = 0 } = opts;
  const params = new URLSearchParams({
    autoplay: "1",
    mute: muted ? "1" : "0",
    controls: controls ? "1" : "0",
    playsinline: "1",
    rel: "0",
    modestbranding: "1",
    iv_load_policy: "3",
    disablekb: controls ? "0" : "1",
    enablejsapi: "1",
    ...(loop ? { loop: "1", playlist: key } : {}),
    ...(start ? { start: String(start) } : {}),
  });
  return `https://www.youtube-nocookie.com/embed/${key}?${params}`;
}

/** Control a YouTube iframe (enablejsapi=1) without loading the IFrame API script. */
export function ytCommand(iframe: HTMLIFrameElement | null, func: "mute" | "unMute" | "playVideo" | "pauseVideo") {
  iframe?.contentWindow?.postMessage(JSON.stringify({ event: "command", func, args: [] }), "*");
}

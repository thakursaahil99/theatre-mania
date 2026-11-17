"use client";

import { Play } from "lucide-react";
import { useState } from "react";

import { Magnetic } from "@/components/ui/Magnetic";
import { Modal } from "@/components/ui/Modal";
import { youtubeEmbed } from "@/lib/trailers";
import type { Video } from "@/lib/types";

export function TrailerModal({ video, open, onClose }: { video: Video | null; open: boolean; onClose: () => void }) {
  return (
    <Modal open={open && !!video} onClose={onClose} label={video?.name ?? "Trailer"}>
      {video && (
        <div className="aspect-video overflow-hidden rounded-2xl bg-black shadow-2xl ring-1 ring-white/10">
          <iframe
            title={video.name}
            src={youtubeEmbed(video.key, { muted: false, controls: true, loop: false })}
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            allowFullScreen
            className="size-full border-0"
          />
        </div>
      )}
    </Modal>
  );
}

export function TrailerButton({ video, label = "Watch Trailer", variant = "primary" }: {
  video: Video | null;
  label?: string;
  variant?: "primary" | "ghost";
}) {
  const [open, setOpen] = useState(false);
  if (!video) return null;
  return (
    <>
      <Magnetic>
        <button onClick={() => setOpen(true)} className={variant === "primary" ? "btn-primary" : "btn-ghost"}>
          <Play className="size-4 fill-current" /> {label}
        </button>
      </Magnetic>
      <TrailerModal video={video} open={open} onClose={() => setOpen(false)} />
    </>
  );
}

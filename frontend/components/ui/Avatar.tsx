import { cn } from "@/lib/utils";

// Keys must match backend/app/schemas/profile.py `Avatar`.
export const AVATARS: Record<string, { from: string; to: string; face: "smile" | "wink" | "cool" | "grin" }> = {
  nebula: { from: "#7c5cff", to: "#ff3d81", face: "smile" },
  ember: { from: "#ff7a18", to: "#ff2e63", face: "grin" },
  aurora: { from: "#00d2a8", to: "#4f7cff", face: "wink" },
  noir: { from: "#3a3f58", to: "#0d0f18", face: "cool" },
  neon: { from: "#f72585", to: "#7209b7", face: "grin" },
  solar: { from: "#ffd166", to: "#ff8c42", face: "smile" },
  tide: { from: "#06b6d4", to: "#1e3a8a", face: "cool" },
  orchid: { from: "#e879f9", to: "#8b5cf6", face: "wink" },
  volt: { from: "#a3e635", to: "#059669", face: "grin" },
  frost: { from: "#bae6fd", to: "#6366f1", face: "smile" },
  dune: { from: "#d6a26b", to: "#7c4a2d", face: "cool" },
  rose: { from: "#fda4af", to: "#e11d48", face: "wink" },
};
export const AVATAR_KEYS = Object.keys(AVATARS);

export function Avatar({ avatar, className, label }: { avatar: string; className?: string; label?: string }) {
  const a = AVATARS[avatar] ?? AVATARS.nebula;
  const id = `av-${avatar}`;
  return (
    <svg viewBox="0 0 100 100" className={cn("rounded-[22%]", className)} role={label ? "img" : undefined}
      aria-label={label} aria-hidden={label ? undefined : true}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={a.from} />
          <stop offset="100%" stopColor={a.to} />
        </linearGradient>
      </defs>
      <rect width="100" height="100" rx="22" fill={`url(#${id})`} />
      <circle cx="78" cy="18" r="30" fill="#fff" opacity="0.08" />
      {a.face === "cool" ? (
        <rect x="24" y="36" width="52" height="12" rx="6" fill="#0b0d16" opacity="0.85" />
      ) : (
        <>
          <circle cx="35" cy="42" r="6" fill="#0b0d16" opacity="0.85" />
          {a.face === "wink" ? (
            <path d="M58 42 h12" stroke="#0b0d16" strokeWidth="5" strokeLinecap="round" opacity="0.85" />
          ) : (
            <circle cx="65" cy="42" r="6" fill="#0b0d16" opacity="0.85" />
          )}
        </>
      )}
      <path
        d={a.face === "grin" ? "M30 62 Q50 82 70 62 Z" : "M32 64 Q50 78 68 64"}
        stroke="#0b0d16"
        strokeWidth="5"
        strokeLinecap="round"
        fill={a.face === "grin" ? "#0b0d16" : "none"}
        opacity="0.85"
      />
    </svg>
  );
}

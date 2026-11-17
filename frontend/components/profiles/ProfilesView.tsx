"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Pencil, Plus } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/providers/AuthProvider";
import { AVATAR_KEYS, Avatar } from "@/components/ui/Avatar";
import { Modal } from "@/components/ui/Modal";
import { ApiError, api } from "@/lib/api";
import type { Profile } from "@/lib/types";
import { cn } from "@/lib/utils";

const MAX_PROFILES = 4;

export function ProfilesView() {
  const router = useRouter();
  const params = useSearchParams();
  const { profiles, selectProfile, reload, loading } = useAuth();
  const [manage, setManage] = useState(params.get("manage") === "1");
  const [editing, setEditing] = useState<Profile | "new" | null>(null);
  const next = params.get("next");

  const choose = async (p: Profile) => {
    if (manage) return setEditing(p);
    await selectProfile(p.id);
    router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    router.refresh();
  };

  return (
    <div className="grid min-h-svh place-items-center px-4 py-28">
      <div className="text-center">
        <motion.h1 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="font-display text-[clamp(2.4rem,6vw,4.5rem)] tracking-wide">
          {manage ? "Manage profiles" : "Who's watching?"}
        </motion.h1>

        <motion.ul className="mt-12 flex flex-wrap justify-center gap-6 md:gap-10" initial="hidden" animate="show"
          variants={{ show: { transition: { staggerChildren: 0.08, delayChildren: 0.15 } } }}>
          {loading && Array.from({ length: 2 }).map((_, i) => <li key={i} className="shimmer size-28 rounded-[22%] md:size-36" />)}
          {profiles.map((p) => (
            <motion.li key={p.id} variants={{ hidden: { opacity: 0, y: 30, scale: 0.9 }, show: { opacity: 1, y: 0, scale: 1 } }}>
              <button onClick={() => choose(p)} className="group flex flex-col items-center gap-3" aria-label={manage ? `Edit ${p.name}` : `Watch as ${p.name}`}>
                <span className="relative">
                  <Avatar avatar={p.avatar} className="size-28 transition duration-300 group-hover:scale-105 group-hover:ring-4 group-hover:ring-white md:size-36 rounded-[22%]" />
                  {manage && (
                    <span className="absolute inset-0 grid place-items-center rounded-[22%] bg-black/55">
                      <Pencil className="size-7" />
                    </span>
                  )}
                  {p.is_kids && <span className="absolute -bottom-2 left-1/2 -translate-x-1/2 rounded-full bg-gold px-2 text-[10px] font-bold text-ink-950">KIDS</span>}
                </span>
                <span className="text-white/60 transition group-hover:text-white">{p.name}</span>
              </button>
            </motion.li>
          ))}
          {!loading && profiles.length < MAX_PROFILES && (
            <motion.li variants={{ hidden: { opacity: 0, y: 30 }, show: { opacity: 1, y: 0 } }}>
              <button onClick={() => setEditing("new")} className="group flex flex-col items-center gap-3">
                <span className="grid size-28 place-items-center rounded-[22%] border-2 border-dashed border-white/20 transition group-hover:border-white/60 group-hover:bg-white/5 md:size-36">
                  <Plus className="size-10 text-white/50 group-hover:text-white" />
                </span>
                <span className="text-white/60 group-hover:text-white">Add profile</span>
              </button>
            </motion.li>
          )}
        </motion.ul>

        <button onClick={() => setManage((m) => !m)} className={cn("mt-14", manage ? "btn-primary" : "btn-ghost")}>
          {manage ? "Done" : "Manage profiles"}
        </button>
      </div>

      <ProfileEditor key={editing === "new" ? "new" : editing?.id} profile={editing} canDelete={profiles.length > 1}
        onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await reload(); }} />
    </div>
  );
}

function ProfileEditor({ profile, canDelete, onClose, onSaved }: {
  profile: Profile | "new" | null;
  canDelete: boolean;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const existing = profile && profile !== "new" ? profile : null;
  const [name, setName] = useState(existing?.name ?? "");
  const [avatar, setAvatar] = useState(existing?.avatar ?? AVATAR_KEYS[Math.floor(Math.random() * AVATAR_KEYS.length)]);
  const [kids, setKids] = useState(existing?.is_kids ?? false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    const body = { name: name.trim(), avatar, is_kids: kids };
    void run(() => existing ? api(`/profiles/${existing.id}`, { method: "PATCH", json: body }) : api("/profiles", { method: "POST", json: body }));
  };

  return (
    <Modal open={profile !== null} onClose={onClose} label={existing ? "Edit profile" : "Add profile"} className="max-w-lg">
      <form onSubmit={save} className="rounded-3xl glass p-6 md:p-8">
        <h2 className="text-xl font-semibold">{existing ? "Edit profile" : "Add a profile"}</h2>
        <div className="mt-6 flex items-center gap-5">
          <AnimatePresence mode="wait">
            <motion.span key={avatar} initial={{ scale: 0.6, rotate: -10, opacity: 0 }} animate={{ scale: 1, rotate: 0, opacity: 1 }}
              exit={{ scale: 0.6, opacity: 0 }} transition={{ type: "spring", stiffness: 300, damping: 20 }}>
              <Avatar avatar={avatar} className="size-20" />
            </motion.span>
          </AnimatePresence>
          <input className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" maxLength={30}
            required aria-label="Profile name" autoFocus />
        </div>
        <p className="mb-3 mt-6 text-xs uppercase tracking-[0.2em] text-white/40">Choose an avatar</p>
        <div className="grid grid-cols-6 gap-3" role="radiogroup" aria-label="Avatar">
          {AVATAR_KEYS.map((key) => (
            <button key={key} type="button" role="radio" aria-checked={avatar === key} aria-label={key} onClick={() => setAvatar(key)}
              className={cn("rounded-[22%] transition hover:scale-110", avatar === key && "ring-2 ring-white ring-offset-2 ring-offset-ink-900")}>
              <Avatar avatar={key} className="w-full" />
            </button>
          ))}
        </div>
        <label className="mt-6 flex cursor-pointer items-center justify-between rounded-xl border border-white/10 px-4 py-3">
          <span>
            <span className="block text-sm font-medium">Kids profile</span>
            <span className="text-xs text-white/45">A simpler experience for younger viewers</span>
          </span>
          <input type="checkbox" checked={kids} onChange={(e) => setKids(e.target.checked)} className="size-5 accent-accent" />
        </label>
        {error && <p role="alert" className="mt-4 text-sm text-danger">{error}</p>}
        <div className="mt-8 flex items-center gap-3">
          <button type="submit" disabled={busy || !name.trim()} className="btn-brand">Save</button>
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          {existing && canDelete && (
            <button type="button" disabled={busy} className="ml-auto text-sm text-danger hover:underline"
              onClick={() => confirm(`Delete ${existing.name}? Their list and history will be removed.`) &&
                void run(() => api(`/profiles/${existing.id}`, { method: "DELETE" }))}>
              Delete
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}

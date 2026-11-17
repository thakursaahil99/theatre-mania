"use client";

import { motion } from "framer-motion";
import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Logo } from "@/components/layout/Navbar";
import { useAuth } from "@/components/providers/AuthProvider";
import { ApiError, api } from "@/lib/api";
import type { Profile, Session } from "@/lib/types";

const OAUTH_ERRORS: Record<string, string> = {
  oauth: "Google sign-in didn't complete. Please try again.",
  email_in_use: "That email already has a password account. Sign in with your password.",
};

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const params = useSearchParams();
  const { setSession } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(OAUTH_ERRORS[params.get("error") ?? ""] ?? null);
  const next = safeNext(params.get("next"));
  const google = process.env.NEXT_PUBLIC_GOOGLE_AUTH === "true";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await api<Session>(mode === "login" ? "/auth/login" : "/auth/signup", {
        method: "POST",
        json: mode === "login" ? { email, password } : { email, password, display_name: name || undefined },
      });
      await setSession(session);
      const profiles = await api<Profile[]>("/profiles");
      // More than one profile and none chosen yet → "Who's watching?"
      if (profiles.length > 1 && !session.active_profile_id) router.replace(`/profiles?next=${encodeURIComponent(next)}`);
      else router.replace(next);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative grid min-h-svh place-items-center overflow-hidden px-4 py-24">
      <div aria-hidden className="absolute inset-0 grain">
        <div className="absolute -left-40 top-10 size-[38rem] animate-float rounded-full bg-accent/25 blur-[130px]" />
        <div className="absolute -right-40 bottom-0 size-[34rem] animate-float rounded-full bg-accent-2/20 blur-[130px] [animation-delay:-3s]" />
      </div>
      <motion.div initial={{ opacity: 0, y: 30, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }} className="relative w-full max-w-md rounded-3xl glass p-8 shadow-2xl md:p-10">
        <Logo className="mb-8 justify-center" />
        <h1 className="text-center text-2xl font-semibold">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p className="mt-2 text-center text-sm text-white/55">
          {mode === "login" ? "Sign in to pick up where you left off." : "Free forever. No ads, no card required."}
        </p>

        <form onSubmit={submit} className="mt-8 space-y-4" noValidate>
          {mode === "signup" && (
            <input className="field" placeholder="Your name (optional)" value={name} onChange={(e) => setName(e.target.value)}
              autoComplete="name" maxLength={80} aria-label="Name" />
          )}
          <input className="field" type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)}
            autoComplete="email" required aria-label="Email" />
          <div className="relative">
            <input className="field pr-12" type={show ? "text" : "password"} placeholder="Password" value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"}
              required minLength={mode === "signup" ? 8 : 1} aria-label="Password" />
            <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}
              className="absolute right-3 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-full text-white/50 hover:text-white">
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
          {mode === "signup" && <p className="text-xs text-white/40">At least 8 characters, mixing letters with numbers or symbols.</p>}
          {error && (
            <motion.p role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
              className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
              {error}
            </motion.p>
          )}
          <button type="submit" disabled={busy || !email || !password} className="btn-brand w-full py-3.5">
            {busy && <LoaderCircle className="size-4 animate-spin" />}
            {mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        {google && (
          <>
            <div className="my-6 flex items-center gap-3 text-xs text-white/35">
              <span className="h-px flex-1 bg-white/10" /> OR <span className="h-px flex-1 bg-white/10" />
            </div>
            <a href={`/api/v1/auth/google/login?next=${encodeURIComponent(next === "/" ? "/profiles" : next)}`} className="btn-ghost w-full">
              <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
                <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6-2.7-6-6.1s2.7-6.1 6-6.1c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.8 3.3 14.6 2.4 12 2.4 6.7 2.4 2.4 6.7 2.4 12s4.3 9.6 9.6 9.6c5.5 0 9.2-3.9 9.2-9.4 0-.6-.1-1.1-.2-1.6H12z" />
              </svg>
              Continue with Google
            </a>
          </>
        )}

        <p className="mt-8 text-center text-sm text-white/55">
          {mode === "login" ? "New to Theatre Mania? " : "Already have an account? "}
          <Link href={`/${mode === "login" ? "signup" : "login"}${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`}
            className="font-medium text-white underline-offset-4 hover:underline">
            {mode === "login" ? "Create an account" : "Sign in"}
          </Link>
        </p>
      </motion.div>
    </div>
  );
}

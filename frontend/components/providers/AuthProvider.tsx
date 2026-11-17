"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import type { Profile, Session, User } from "@/lib/types";

interface AuthState {
  user: User | null;
  profiles: Profile[];
  activeProfile: Profile | null;
  loading: boolean;
  reload: () => Promise<void>;
  selectProfile: (id: string) => Promise<void>;
  logout: () => Promise<void>;
  setSession: (s: Session) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const setSession = useCallback(async (session: Session) => {
    setUser(session.user);
    const list = await api<Profile[]>("/profiles");
    setProfiles(list);
    setActiveId(session.active_profile_id ?? (list.length === 1 ? list[0].id : null));
  }, []);

  const reload = useCallback(async () => {
    try {
      await setSession(await api<Session>("/auth/me"));
    } catch {
      setUser(null);
      setProfiles([]);
      setActiveId(null);
    } finally {
      setLoading(false);
    }
  }, [setSession]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const selectProfile = useCallback(async (id: string) => {
    await api(`/profiles/${id}/select`, { method: "POST" });
    setActiveId(id);
  }, []);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
    setProfiles([]);
    setActiveId(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      profiles,
      activeProfile: profiles.find((p) => p.id === activeId) ?? profiles[0] ?? null,
      loading,
      reload,
      selectProfile,
      logout,
      setSession,
    }),
    [user, profiles, activeId, loading, reload, selectProfile, logout, setSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

"use client";

import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "framer-motion";
import { LayoutDashboard, LogOut, Search, UserCog } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/providers/AuthProvider";
import { Avatar } from "@/components/ui/Avatar";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/bollywood", label: "Bollywood" },
  { href: "/browse/free", label: "Free to Watch" },
  { href: "/browse/trending", label: "Trending" },
  { href: "/browse/top_rated", label: "Top Rated" },
  { href: "/my-list", label: "My List" },
];

export function Logo({ className }: { className?: string }) {
  return (
    <Link href="/" aria-label="Theatre Mania home" className={cn("group flex items-center gap-2", className)}>
      <span className="relative grid size-8 place-items-center overflow-hidden rounded-lg brand-gradient">
        <span className="absolute inset-0 translate-x-[-120%] bg-white/30 blur-sm transition-transform duration-700 group-hover:translate-x-[120%]" />
        <svg viewBox="0 0 24 24" className="size-4 fill-white" aria-hidden><path d="M8 5.5v13l10.5-6.5z" /></svg>
      </span>
      <span className="font-display text-2xl tracking-[0.14em] text-white">THEATRE<span className="text-gradient">MANIA</span></span>
    </Link>
  );
}

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, activeProfile, profiles, selectProfile, logout } = useAuth();
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [menu, setMenu] = useState(false);

  useMotionValueEvent(scrollY, "change", (y) => {
    const prev = scrollY.getPrevious() ?? 0;
    setScrolled(y > 24);
    setHidden(y > 320 && y > prev + 4 && !menu);
    if (y < prev - 4) setHidden(false);
  });

  if (pathname.startsWith("/watch") || pathname.startsWith("/admin")) return null;

  return (
    <motion.header
      className="fixed inset-x-0 top-0 z-40"
      animate={{ y: hidden ? "-100%" : "0%" }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    >
      <div
        className={cn(
          "flex h-[var(--nav-h)] items-center gap-8 px-4 transition-[background,backdrop-filter,border-color] duration-500 md:px-12",
          scrolled ? "glass border-x-0 border-t-0" : "border-b border-transparent bg-linear-to-b from-black/70 to-transparent",
        )}
      >
        <Logo />
        <nav aria-label="Primary" className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <Link key={l.href} href={l.href}
                className={cn("relative rounded-full px-3.5 py-1.5 text-sm transition-colors",
                  active ? "text-white" : "text-white/60 hover:text-white")}>
                {active && <motion.span layoutId="nav-pill" className="absolute inset-0 -z-10 rounded-full bg-white/10"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }} />}
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <Link href="/search" aria-label="Search"
            className="grid size-10 place-items-center rounded-full text-white/80 transition hover:bg-white/10 hover:text-white">
            <Search className="size-5" />
          </Link>
          {user ? (
            <div className="relative hidden md:block" onMouseLeave={() => setMenu(false)}>
              <button onClick={() => setMenu((m) => !m)} onMouseEnter={() => setMenu(true)} aria-haspopup="menu" aria-expanded={menu}
                className="flex items-center gap-2 rounded-full p-1 transition hover:bg-white/10">
                <Avatar avatar={activeProfile?.avatar ?? "nebula"} className="size-8" />
              </button>
              <AnimatePresence>
                {menu && (
                  <motion.div role="menu" initial={{ opacity: 0, y: -8, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -6, scale: 0.98 }} transition={{ duration: 0.18 }}
                    className="absolute right-0 top-full mt-2 w-60 overflow-hidden rounded-2xl glass p-2 shadow-2xl">
                    {profiles.map((p) => (
                      <button key={p.id} role="menuitem" onClick={async () => { await selectProfile(p.id); setMenu(false); router.refresh(); }}
                        className={cn("flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left text-sm transition hover:bg-white/10",
                          p.id === activeProfile?.id && "bg-white/5")}>
                        <Avatar avatar={p.avatar} className="size-7" />
                        <span className="truncate">{p.name}</span>
                        {p.id === activeProfile?.id && <span className="ml-auto size-1.5 rounded-full bg-accent" />}
                      </button>
                    ))}
                    <div className="my-2 h-px bg-white/10" />
                    <MenuLink href="/profiles?manage=1" icon={<UserCog className="size-4" />}>Manage profiles</MenuLink>
                    <MenuLink href="/history" icon={<span className="size-4 text-center">↺</span>}>Watch history</MenuLink>
                    {user.is_admin && <MenuLink href="/admin" icon={<LayoutDashboard className="size-4" />}>Admin studio</MenuLink>}
                    <button role="menuitem" onClick={async () => { await logout(); router.push("/"); }}
                      className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-white/70 transition hover:bg-white/10 hover:text-white">
                      <LogOut className="size-4" /> Sign out
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <Link href={`/login?next=${encodeURIComponent(pathname)}`} className="btn-brand hidden px-5 py-2 md:inline-flex">
              Sign in
            </Link>
          )}
        </div>
      </div>
    </motion.header>
  );
}

function MenuLink({ href, icon, children }: { href: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <Link href={href} role="menuitem"
      className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-white/70 transition hover:bg-white/10 hover:text-white">
      {icon} {children}
    </Link>
  );
}

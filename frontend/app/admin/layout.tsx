"use client";

import { ArrowLeft, Film, LayoutDashboard, LoaderCircle, PlusCircle, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Logo } from "@/components/layout/Navbar";
import { useAuth } from "@/components/providers/AuthProvider";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/admin", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { href: "/admin/titles", label: "Library", icon: Film, exact: true },
  { href: "/admin/titles/new", label: "Add title", icon: PlusCircle, exact: true },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [loading, user, router, pathname]);

  if (loading || !user) {
    return <div className="grid min-h-svh place-items-center"><LoaderCircle className="size-8 animate-spin text-white/50" /></div>;
  }
  if (!user.is_admin) {
    return (
      <div className="grid min-h-svh place-items-center px-4 text-center">
        <div>
          <ShieldAlert className="mx-auto size-10 text-white/40" />
          <h1 className="mt-4 text-2xl font-semibold">Admins only</h1>
          <p className="mt-2 text-white/55">Your account doesn&apos;t have access to the studio.</p>
          <Link href="/" className="btn-primary mt-8">Back to Theatre Mania</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-svh md:grid md:grid-cols-[240px_1fr]">
      <aside className="sticky top-0 z-30 border-b border-white/5 bg-ink-900/90 backdrop-blur md:h-svh md:border-b-0 md:border-r">
        <div className="flex items-center justify-between gap-4 p-4 md:block md:p-6">
          <Logo />
          <p className="hidden text-[10px] uppercase tracking-[0.3em] text-white/35 md:mt-2 md:block">Studio</p>
        </div>
        <nav aria-label="Admin" className="no-scrollbar flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:px-4">
          {NAV.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link key={href} href={href}
                className={cn("flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition",
                  active ? "bg-white/10 text-white" : "text-white/55 hover:bg-white/5 hover:text-white")}>
                <Icon className="size-4" /> {label}
              </Link>
            );
          })}
          <Link href="/" className="flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-white/40 transition hover:text-white md:mt-6">
            <ArrowLeft className="size-4" /> Back to site
          </Link>
        </nav>
      </aside>
      <div className="min-w-0 px-4 py-8 md:px-10 md:py-10">{children}</div>
    </div>
  );
}

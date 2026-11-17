"use client";

import { motion } from "framer-motion";
import { Bookmark, Clapperboard, Home, Popcorn, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/providers/AuthProvider";
import { Avatar } from "@/components/ui/Avatar";
import { cn } from "@/lib/utils";

export function MobileNav() {
  const pathname = usePathname();
  const { user, activeProfile } = useAuth();
  if (pathname.startsWith("/watch") || pathname.startsWith("/admin")) return null;

  const items = [
    { href: "/", label: "Home", icon: <Home className="size-5" /> },
    { href: "/bollywood", label: "Bollywood", icon: <Popcorn className="size-5" /> },
    { href: "/search", label: "Search", icon: <Search className="size-5" /> },
    { href: "/browse/free", label: "Free", icon: <Clapperboard className="size-5" /> },
    { href: "/my-list", label: "My List", icon: <Bookmark className="size-5" /> },
    {
      href: user ? "/profiles?manage=1" : "/login",
      label: user ? "Profile" : "Sign in",
      icon: <Avatar avatar={activeProfile?.avatar ?? "noir"} className="size-6" />,
    },
  ];

  return (
    <nav aria-label="Mobile" className="fixed inset-x-3 bottom-3 z-40 md:hidden" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      <ul className="glass flex items-center justify-around rounded-2xl px-1 py-1.5 shadow-[0_20px_60px_-20px_rgb(0_0_0/0.9)]">
        {items.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href.split("?")[0]);
          return (
            <li key={item.label} className="flex-1">
              <Link href={item.href}
                className={cn("relative flex flex-col items-center gap-0.5 rounded-xl py-1.5 text-[10px] font-medium transition-colors",
                  active ? "text-white" : "text-white/50")}>
                {active && <motion.span layoutId="mobile-pill" className="absolute inset-0 -z-10 rounded-xl bg-white/10"
                  transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
                {item.icon}
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

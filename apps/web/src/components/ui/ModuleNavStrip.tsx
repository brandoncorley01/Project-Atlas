"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const MODULES = [
  {
    href: "/sports",
    label: "Sports",
    emoji: "🏈",
    featured: true,
    color: "hover:border-violet-500/50 hover:bg-violet-500/10",
    activeClass: "border-violet-500 bg-violet-500/20 text-violet-200 ring-2 ring-violet-500/30",
  },
  {
    href: "/parlays",
    label: "Parlays",
    emoji: "🎯",
    color: "hover:border-orange-500/50 hover:bg-orange-500/10",
    activeClass: "border-orange-500 bg-orange-500/20 text-orange-200",
  },
  {
    href: "/options",
    label: "Options",
    emoji: "📈",
    color: "hover:border-sky-500/50 hover:bg-sky-500/10",
    activeClass: "border-sky-500 bg-sky-500/20 text-sky-200",
  },
  {
    href: "/options-intelligence",
    label: "Opt Intel",
    emoji: "◐",
    color: "hover:border-cyan-500/50 hover:bg-cyan-500/10",
    activeClass: "border-cyan-500 bg-cyan-500/20 text-cyan-200",
  },
  {
    href: "/market-intelligence",
    label: "Market",
    emoji: "▣",
    color: "hover:border-teal-500/50 hover:bg-teal-500/10",
    activeClass: "border-teal-500 bg-teal-500/20 text-teal-200",
  },
  {
    href: "/stocks",
    label: "Stocks",
    emoji: "📊",
    color: "hover:border-emerald-500/50 hover:bg-emerald-500/10",
    activeClass: "border-emerald-500 bg-emerald-500/20 text-emerald-200",
  },
  {
    href: "/news",
    label: "News",
    emoji: "📰",
    color: "hover:border-amber-500/50 hover:bg-amber-500/10",
    activeClass: "border-amber-500 bg-amber-500/20 text-amber-200",
  },
] as const;

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function ModuleNavStrip() {
  const pathname = usePathname();

  return (
    <nav aria-label="Jump to module" className="mb-6 flex gap-2 overflow-x-auto pb-1">
      {MODULES.map((mod) => {
        const active = isActive(pathname, mod.href);
        return (
          <Link
            key={mod.href}
            href={mod.href}
            className={`flex shrink-0 items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold transition-colors ${
              active
                ? mod.activeClass
                : `border-border bg-surface-elevated text-foreground ${mod.color}`
            } ${"featured" in mod && mod.featured && !active ? "ring-1 ring-violet-500/40" : ""}`}
          >
            <span aria-hidden>{mod.emoji}</span>
            {mod.label}
            {"featured" in mod && mod.featured && (
              <span className="rounded bg-violet-600 px-1.5 py-0.5 text-[9px] font-bold text-white">
                24/7
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { isNavActive } from "@/lib/nav-utils";

const primaryTabs = [
  { href: "/", label: "Home", icon: "⌂" },
  { href: "/stocks", label: "Stocks", icon: "📈" },
  { href: "/options", label: "Options", icon: "◐" },
  { href: "/sports", label: "Sports", icon: "◆" },
  { href: "/parlays", label: "Parlays", icon: "◎" },
] as const;

const moreItems = [
  { href: "/options-intelligence", label: "Options Intelligence" },
  { href: "/market-intelligence", label: "Market Intelligence" },
  { href: "/news", label: "News" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/alerts", label: "Alerts" },
  { href: "/performance", label: "Performance" },
  { href: "/#data-providers", label: "Data providers" },
];

export function MobileBottomNav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const moreActive = moreItems.some(
    (item) => item.href.startsWith("/#") ? false : isNavActive(pathname, item.href),
  );

  return (
    <>
      {moreOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/50 sm:hidden"
          aria-label="Close menu"
          onClick={() => setMoreOpen(false)}
        />
      )}

      {moreOpen && (
        <nav className="fixed bottom-[4.5rem] left-4 right-4 z-50 rounded-xl border border-border bg-surface-elevated py-2 shadow-xl sm:hidden">
          <p className="px-4 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted">
            More
          </p>
          {moreItems.map((item) => {
            const active = item.href.startsWith("/#")
              ? false
              : isNavActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMoreOpen(false)}
                className={`block px-4 py-2.5 text-sm ${
                  active
                    ? "bg-accent/15 font-medium text-accent"
                    : "text-foreground hover:bg-surface-hover"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      )}

      <nav
        className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-surface/95 backdrop-blur-md sm:hidden"
        aria-label="Primary navigation"
      >
        <div className="mx-auto flex max-w-lg items-stretch justify-around px-1 pb-[env(safe-area-inset-bottom)]">
          {primaryTabs.map((tab) => {
            const active = isNavActive(pathname, tab.href);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 px-1 py-2.5 text-[10px] font-medium transition-colors ${
                  active ? "text-accent" : "text-muted"
                }`}
              >
                <span className="text-sm leading-none" aria-hidden>
                  {tab.icon}
                </span>
                <span className="truncate">{tab.label}</span>
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setMoreOpen((v) => !v)}
            className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 px-1 py-2.5 text-[10px] font-medium transition-colors ${
              moreActive || moreOpen ? "text-accent" : "text-muted"
            }`}
            aria-expanded={moreOpen}
            aria-label="More pages"
          >
            <span className="text-sm leading-none" aria-hidden>
              ···
            </span>
            <span>More</span>
          </button>
        </div>
      </nav>
    </>
  );
}

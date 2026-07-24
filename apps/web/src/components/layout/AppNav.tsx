"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isNavActive } from "@/lib/nav-utils";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/stocks", label: "Stocks" },
  { href: "/options", label: "Options" },
  { href: "/options-intelligence", label: "Opt Intel" },
  { href: "/market-intelligence", label: "Market Intel" },
  { href: "/sports", label: "Sports" },
  { href: "/parlays", label: "Parlays" },
  { href: "/news", label: "News" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/alerts", label: "Alerts" },
  { href: "/performance", label: "Performance" },
];

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="hidden min-w-0 flex-1 gap-0.5 overflow-x-auto sm:flex">
      {navItems.map((item) => {
        const active = isNavActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`shrink-0 rounded-md px-2.5 py-1.5 text-sm transition-colors lg:px-3 ${
              active
                ? "bg-accent/20 font-medium text-accent"
                : "text-muted hover:bg-surface-hover hover:text-foreground"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

import Link from "next/link";
import { AppNav } from "@/components/layout/AppNav";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { UserMenu } from "@/components/layout/UserMenu";

interface AppShellProps {
  children: React.ReactNode;
  userEmail?: string;
}

export function AppShell({ children, userEmail }: AppShellProps) {
  return (
    <div className="flex min-h-screen w-full min-w-0 flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:gap-4">
          <Link href="/" className="shrink-0 text-lg font-bold tracking-tight text-accent">
            Atlas
          </Link>
          <AppNav />
          <div className="ml-auto shrink-0">{userEmail && <UserMenu email={userEmail} />}</div>
        </div>
      </header>

      <div className="border-b border-warning/25 bg-warning/8 px-4 py-2 text-center text-xs leading-relaxed text-warning/90">
        Decision support only — not financial advice. Trade and bet at your own risk.
      </div>

      <main className="mx-auto w-full min-w-0 max-w-7xl flex-1 px-4 py-6 pb-24 sm:pb-6">{children}</main>

      <MobileBottomNav />
    </div>
  );
}

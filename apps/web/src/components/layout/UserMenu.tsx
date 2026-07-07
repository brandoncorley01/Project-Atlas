"use client";

import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { RestartApiButton } from "@/components/ui/RestartApiButton";

interface UserMenuProps {
  email: string;
}

export function UserMenu({ email }: UserMenuProps) {
  const router = useRouter();

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="flex items-center gap-2 sm:gap-3">
      <span className="hidden max-w-[140px] truncate text-sm text-muted md:inline lg:max-w-none">{email}</span>
      <RestartApiButton />
      <button
        type="button"
        onClick={handleSignOut}
        className="rounded-md border border-border px-2.5 py-1.5 text-sm text-muted transition-colors hover:bg-surface-hover hover:text-foreground sm:px-3"
      >
        Sign out
      </button>
    </div>
  );
}

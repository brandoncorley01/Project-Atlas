import { AppShell } from "@/components/layout/AppShell";
import { MarketScanBar } from "@/components/dashboard/MarketScanBar";
import { ModuleNavStrip } from "@/components/ui/ModuleNavStrip";
import { BackendStatusBar } from "@/components/ui/BackendStatusBar";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  let userEmail: string | undefined;

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    userEmail = user?.email;
  }

  return (
    <AppShell userEmail={userEmail}>
      {userEmail && <MarketScanBar />}
      {userEmail && <ModuleNavStrip />}
      {children}
      <BackendStatusBar />
    </AppShell>
  );
}

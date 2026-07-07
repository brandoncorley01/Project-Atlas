import { AlertsView, type AlertItem } from "@/components/alerts/AlertsView";
import { PageHeader } from "@/components/ui/PageHeader";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface AlertsResponse {
  items: AlertItem[];
}

export default async function AlertsPage() {
  let items: AlertItem[] = [];

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        const data = await apiFetch<AlertsResponse>("/alerts?limit=50", token);
        items = data.items;
      } catch {
        items = [];
      }
    }
  }

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Atlas notifies you when a scan finds an especially strong signal. Tap any alert to jump to the full play."
      />
      <AlertsView initialItems={items} />
    </>
  );
}

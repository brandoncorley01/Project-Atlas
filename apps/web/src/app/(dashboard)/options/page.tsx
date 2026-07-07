import { OptionsSignalsView } from "@/components/options/OptionsSignalsView";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { QuickStartGuide } from "@/components/ui/QuickStartGuide";
import type { OptionSignal } from "@/components/options/OptionSignalCard";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface OptionsListResponse {
  items: OptionSignal[];
}

async function loadOptions(path: string, token: string) {
  try {
    const data = await apiFetch<OptionsListResponse>(path, token);
    return data.items;
  } catch {
    return [];
  }
}

export default async function OptionsPage() {
  let allItems: OptionSignal[] = [];
  let budgetItems: OptionSignal[] = [];

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      allItems = await loadOptions("/signals/options?limit=20", token);
      budgetItems = await loadOptions("/signals/options?limit=12&budget=true", token);
    }
  }

  const hasAny = allItems.length > 0 || budgetItems.length > 0;

  return (
    <>
      <PageHeader
        title="Retail Options"
        description="Atlas ranks call and put setups by confidence and profit odds. Pick #1 for the strongest play — expand any card for entry dates, breakeven, and beginner tips."
      />

      {!hasAny && <QuickStartGuide compact />}

      {hasAny ? (
        <OptionsSignalsView allItems={allItems} budgetItems={budgetItems} />
      ) : (
        <EmptyState
          title="No options picks yet"
          description='Click "Deep scan market" in the scanner bar above. Atlas will rank opportunities — look for high Confidence and Opportunity scores.'
        />
      )}
    </>
  );
}

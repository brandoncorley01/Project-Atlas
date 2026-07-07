"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

export function GenerateSignalsButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleGenerate() {
    setLoading(true);
    setMessage(null);

    let token: string | undefined;
    if (!usesBffProxy()) {
      const { createClient } = await import("@/lib/supabase/client");
      const { data: sessionData } = await createClient().auth.getSession();
      token = sessionData.session?.access_token ?? undefined;
      if (!token) {
        setMessage("Not signed in");
        setLoading(false);
        return;
      }
    }

    const apiUrl = getApiUrl();
    const response = await fetch(`${apiUrl}/engine/run-mock`, {
      method: "POST",
      headers: apiRequestHeaders(token),
    });

    const data = await response.json();
    setLoading(false);

    if (!response.ok) {
      setMessage(data.detail ?? "Failed to generate signals");
      return;
    }

    setMessage(`Created ${data.signals_created} signals (${data.filtered_out} filtered out)`);
    router.refresh();
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <button
        type="button"
        onClick={handleGenerate}
        disabled={loading}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {loading ? "Generating…" : "Generate mock signals"}
      </button>
      {message && <p className="text-xs text-muted">{message}</p>}
    </div>
  );
}

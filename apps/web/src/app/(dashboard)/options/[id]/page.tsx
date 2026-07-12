import Link from "next/link";
import { OptionSignalCard, type OptionSignal } from "@/components/options/OptionSignalCard";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

export default async function OptionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let signal: OptionSignal | null = null;

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        signal = await apiFetch<OptionSignal>(`/signals/options/${id}`, token);
      } catch {
        signal = null;
      }
    }
  }

  if (!signal) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface/50 p-8 text-center text-muted">
        Options signal not found.{" "}
        <Link href="/options" className="text-accent underline">
          Back to options
        </Link>
      </div>
    );
  }

  const optionType = (signal.option_type ?? "option").toUpperCase();

  return (
    <>
      <div className="mb-6">
        <Link href="/options" className="text-sm text-accent hover:underline">
          ← All options picks
        </Link>
        <h1 className="mt-2 text-2xl font-bold">
          {signal.underlying} {optionType} ${Number(signal.strike ?? 0).toFixed(0)} detail
        </h1>
        <p className="mt-1 text-sm text-muted">
          Review the trade plan and log win/loss when you close the position.
        </p>
      </div>
      <OptionSignalCard row={signal} rank={1} />
    </>
  );
}

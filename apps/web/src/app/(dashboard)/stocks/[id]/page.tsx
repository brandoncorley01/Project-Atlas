import Link from "next/link";
import { StockSignalCard, type StockSignal } from "@/components/stocks/StockSignalCard";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

export default async function StockDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let signal: StockSignal | null = null;

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        signal = await apiFetch<StockSignal>(`/signals/stocks/${id}`, token);
      } catch {
        signal = null;
      }
    }
  }

  if (!signal) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface/50 p-8 text-center text-muted">
        Stock signal not found.{" "}
        <Link href="/stocks" className="text-accent underline">
          Back to stocks
        </Link>
      </div>
    );
  }

  return (
    <>
      <div className="mb-6">
        <Link href="/stocks" className="text-sm text-accent hover:underline">
          ← All stock swings
        </Link>
        <h1 className="mt-2 text-2xl font-bold">
          {signal.ticker} swing detail
        </h1>
      </div>
      <StockSignalCard row={signal} rank={1} showChart />
    </>
  );
}

import Link from "next/link";
import { ParlayCard, type Parlay } from "@/components/parlays/ParlayCard";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

export default async function ParlayDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let parlay: Parlay | null = null;

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        parlay = await apiFetch<Parlay>(`/parlays/${id}`, token);
      } catch {
        parlay = null;
      }
    }
  }

  if (!parlay) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface/50 p-8 text-center text-muted">
        Parlay not found.{" "}
        <Link href="/parlays" className="text-accent underline">
          Back to parlays
        </Link>
      </div>
    );
  }

  return (
    <>
      <div className="mb-6">
        <Link href="/parlays" className="text-sm text-accent hover:underline">
          ← All parlays
        </Link>
        <h1 className="mt-2 text-2xl font-bold">{parlay.name ?? "Parlay detail"}</h1>
      </div>
      <ParlayCard row={parlay} rank={1} />
    </>
  );
}

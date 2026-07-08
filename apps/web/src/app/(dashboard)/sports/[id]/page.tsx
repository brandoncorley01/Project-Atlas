import Link from "next/link";
import { SportsSignalCard, type SportsSignal } from "@/components/sports/SportsSignalCard";
import { CATEGORY_SLUG_LABELS } from "@/lib/sports-categories";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

export default async function SportsDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let signal: SportsSignal | null = null;

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        signal = await apiFetch<SportsSignal>(`/signals/sports/${id}`, token);
      } catch {
        signal = null;
      }
    }
  }

  if (!signal) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface/50 p-8 text-center text-muted">
        Sports signal not found.{" "}
        <Link href="/sports" className="text-accent underline">
          Back to sports
        </Link>
      </div>
    );
  }

  return (
    <>
      <div className="mb-6">
        <Link href="/sports" className="text-sm text-accent hover:underline">
          ← All sports signals
        </Link>
        {signal.categories && signal.categories.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {signal.categories.map((slug) => (
              <Link
                key={slug}
                href={`/sports/category/${slug}`}
                className="rounded-full bg-violet-500/20 px-2 py-0.5 text-xs font-medium text-violet-300 hover:bg-violet-500/30"
              >
                {CATEGORY_SLUG_LABELS[slug] ?? slug.replace(/_/g, " ")}
              </Link>
            ))}
          </div>
        )}
        <h1 className="mt-2 break-words text-2xl font-bold">
          {signal.selection} · {signal.sport}
        </h1>
      </div>
      <SportsSignalCard row={signal} rank={1} />
    </>
  );
}

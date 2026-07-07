import Link from "next/link";
import { ParlayCategoryGuide } from "@/components/parlays/ParlayCategoryGuide";
import { ParlayCard, type Parlay } from "@/components/parlays/ParlayCard";
import type { ParlayCategoryMeta } from "@/lib/parlay-categories";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface CategoryDetailResponse extends ParlayCategoryMeta {
  items: Parlay[];
}

export default async function ParlayCategoryPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let detail: CategoryDetailResponse | null = null;

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        detail = await apiFetch<CategoryDetailResponse>(
          `/parlays/categories/${slug}?limit=20`,
          token,
        );
      } catch {
        detail = null;
      }
    }
  }

  if (!detail) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface/50 p-8 text-center text-muted">
        Category not found.{" "}
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
        <h1 className="mt-2 text-2xl font-bold">{detail.title}</h1>
        <p className="mt-1 text-sm text-muted">{detail.description}</p>
      </div>

      <ParlayCategoryGuide category={detail} />

      {detail.items.length > 0 ? (
        <div className="space-y-4">
          {detail.items.map((item, index) => (
            <ParlayCard key={item.id} row={item} rank={index + 1} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border bg-surface/50 p-8 text-center text-muted">
          No parlays in this category yet. Scan sports odds and build parlays from the main page.
        </div>
      )}
    </>
  );
}

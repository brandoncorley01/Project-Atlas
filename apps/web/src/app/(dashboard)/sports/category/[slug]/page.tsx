import Link from "next/link";
import { SportsCategoryGuide } from "@/components/sports/SportsCategoryGuide";
import { SportsSignalCard, type SportsSignal } from "@/components/sports/SportsSignalCard";
import type { SportsCategoryMeta } from "@/lib/sports-categories";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface CategoryDetailResponse extends SportsCategoryMeta {
  items: SportsSignal[];
}

export default async function SportsCategoryPage({
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
          `/signals/sports/categories/${slug}?limit=30`,
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
        <h1 className="mt-2 text-2xl font-bold">{detail.title}</h1>
        <p className="mt-1 text-sm text-muted">{detail.description}</p>
      </div>

      <SportsCategoryGuide category={detail} />

      {detail.items.length > 0 ? (
        <div className="space-y-4">
          {detail.items.map((item, index) => (
            <SportsSignalCard key={item.id} row={item} rank={index + 1} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border bg-surface/50 p-8 text-center text-muted">
          No plays in this category yet. Run a sports scan from the main sports page.
        </div>
      )}
    </>
  );
}

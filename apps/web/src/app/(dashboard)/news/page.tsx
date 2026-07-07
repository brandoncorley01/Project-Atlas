import { NewsBoard } from "@/components/news/NewsBoard";
import { PageHeader } from "@/components/ui/PageHeader";
import type { NewsItem } from "@/components/news/NewsCard";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface NewsResponse {
  items: NewsItem[];
}

export default async function NewsPage() {
  let items: NewsItem[] = [];

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        const data = await apiFetch<NewsResponse>("/news?limit=40", token);
        items = data.items;
      } catch {
        items = [];
      }
    }
  }

  return (
    <>
      <PageHeader
        title="News Catalyst Board"
        description="Headlines ranked by impact and sentiment. Every story links to the original source — read the full article, then run a market scan to find trades the news supports."
      />
      <NewsBoard initialItems={items} />
    </>
  );
}

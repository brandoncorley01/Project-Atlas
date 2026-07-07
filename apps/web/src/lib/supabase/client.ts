import { createBrowserClient } from "@supabase/ssr";
import { getSupabaseEnv } from "@/lib/env";

export function createClient() {
  const env = getSupabaseEnv();
  if (!env) {
    throw new Error("Supabase is not configured. Visit /setup to add your keys.");
  }

  return createBrowserClient(env.url, env.anonKey);
}

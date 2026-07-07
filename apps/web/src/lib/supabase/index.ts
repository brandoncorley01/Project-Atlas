import { getSupabaseEnv } from "@/lib/env";
import { createClient as createBrowserClient } from "@/lib/supabase/client";
import { createClient as createServerClient } from "@/lib/supabase/server";

export { createBrowserClient as createClient };
export { createServerClient };

export async function getSupabaseOrNull() {
  if (!getSupabaseEnv()) return null;
  return createServerClient();
}

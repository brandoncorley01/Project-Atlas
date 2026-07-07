function isValidPublicKey(key: string): boolean {
  return key.startsWith("eyJ") || key.startsWith("sb_publishable_");
}

function isValidSecretKey(key: string): boolean {
  return key.startsWith("eyJ") || key.startsWith("sb_secret_");
}

export function isSupabaseConfigured(): boolean {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();

  if (!url || !key) return false;
  if (url.includes("REPLACE") || key.includes("REPLACE")) return false;
  if (!url.startsWith("https://") || !url.includes("supabase.co")) return false;
  if (!isValidPublicKey(key)) return false;

  return true;
}

export function getSupabaseEnv() {
  if (!isSupabaseConfigured()) {
    return null;
  }

  return {
    url: process.env.NEXT_PUBLIC_SUPABASE_URL!.trim(),
    anonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!.trim(),
  };
}

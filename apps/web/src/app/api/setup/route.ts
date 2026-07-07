import { NextResponse } from "next/server";
import { writeFile } from "fs/promises";
import path from "path";

interface SetupBody {
  supabaseUrl?: string;
  anonKey?: string;
  serviceRoleKey?: string;
  jwtSecret?: string;
  userId?: string;
}

function normalizeUrl(url: string): string {
  return url.trim().replace(/\/$/, "");
}

function isValidPublicKey(key: string): boolean {
  return key.startsWith("eyJ") || key.startsWith("sb_publishable_");
}

function isValidSecretKey(key: string): boolean {
  return key.startsWith("eyJ") || key.startsWith("sb_secret_");
}

function validate(body: SetupBody): string | null {
  if (!body.supabaseUrl?.includes("supabase.co")) {
    return "Project URL must be your Supabase URL (https://xxx.supabase.co)";
  }
  if (!body.anonKey || !isValidPublicKey(body.anonKey)) {
    return "Publishable key should start with eyJ... or sb_publishable_...";
  }
  if (!body.serviceRoleKey || !isValidSecretKey(body.serviceRoleKey)) {
    return "Secret key should start with eyJ... or sb_secret_...";
  }
  if (!body.jwtSecret || body.jwtSecret.length < 20) {
    return "JWT secret is required (from Supabase → Settings → API → JWT Settings)";
  }
  if (!body.userId || body.userId.length < 30) {
    return "User UUID is required (from Authentication → Users)";
  }
  return null;
}

export async function POST(request: Request) {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "Setup is disabled in production." }, { status: 403 });
  }

  const body = (await request.json()) as SetupBody;
  const error = validate(body);
  if (error) {
    return NextResponse.json({ error }, { status: 400 });
  }

  const supabaseUrl = normalizeUrl(body.supabaseUrl!);

  const webEnv = `NEXT_PUBLIC_SUPABASE_URL=${supabaseUrl}
NEXT_PUBLIC_SUPABASE_ANON_KEY=${body.anonKey!.trim()}
NEXT_PUBLIC_API_URL=http://127.0.0.1:8012/api/v1
`;

  const apiEnv = `SUPABASE_URL=${supabaseUrl}
SUPABASE_ANON_KEY=${body.anonKey!.trim()}
SUPABASE_SERVICE_ROLE_KEY=${body.serviceRoleKey!.trim()}
SUPABASE_JWT_SECRET=${body.jwtSecret!.trim()}

API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000
CRON_SECRET=dev-cron-secret-change-later

ENVIRONMENT=development
DEFAULT_USER_ID=${body.userId!.trim()}

FINNHUB_API_KEY=
POLYGON_API_KEY=
ODDS_API_KEY=
OPENAI_API_KEY=
`;

  const webEnvPath = path.join(process.cwd(), ".env.local");
  const apiEnvPath = path.join(process.cwd(), "..", "api", ".env");

  try {
    await writeFile(webEnvPath, webEnv, "utf8");
    await writeFile(apiEnvPath, apiEnv, "utf8");
  } catch {
    return NextResponse.json(
      { error: "Could not write env files. Check folder permissions." },
      { status: 500 },
    );
  }

  return NextResponse.json({
    ok: true,
    message: "Environment files saved. Restart both servers, then open /login.",
  });
}

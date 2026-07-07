import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { runApiRestart } from "@/lib/restart-api-server";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

/** Dev-only: restart FastAPI on the dev machine (works from mobile over LAN). */
export async function POST() {
  if (process.env.NODE_ENV !== "development") {
    return NextResponse.json({ detail: "Restart is only available in local dev." }, { status: 404 });
  }

  const supabase = await createClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error || !user) {
    return NextResponse.json({ detail: "Sign in to restart the API." }, { status: 401 });
  }

  const result = await runApiRestart(user.email ?? undefined);
  if (!result.ok) {
    return NextResponse.json(
      { detail: result.detail ?? "Restart script failed. Run npm run dev:restart-api on the PC." },
      { status: 500 },
    );
  }

  return NextResponse.json({
    status: "restarted",
    message: "API restarted successfully.",
  });
}

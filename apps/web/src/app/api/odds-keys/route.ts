import { NextResponse } from "next/server";
import { probeOddsKeysFromEnv } from "@/lib/odds-key-probe";

export async function GET() {
  const result = await probeOddsKeysFromEnv();
  if (result.error) {
    return NextResponse.json(result, { status: 500 });
  }
  return NextResponse.json(result);
}

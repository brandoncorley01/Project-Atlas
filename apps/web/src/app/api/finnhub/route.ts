import { NextResponse } from "next/server";
import { readFile, writeFile } from "fs/promises";
import path from "path";

const API_ENV_PATH = path.join(process.cwd(), "..", "api", ".env");

async function updateFinnhubKey(apiKey: string): Promise<void> {
  let content: string;
  try {
    content = await readFile(API_ENV_PATH, "utf8");
  } catch {
    throw new Error("apps/api/.env not found — complete /setup first");
  }

  const line = `FINNHUB_API_KEY=${apiKey.trim()}`;
  if (/^FINNHUB_API_KEY=.*$/m.test(content)) {
    content = content.replace(/^FINNHUB_API_KEY=.*$/m, line);
  } else {
    content = `${content.trimEnd()}\n${line}\n`;
  }

  await writeFile(API_ENV_PATH, content, "utf8");
}

export async function GET() {
  try {
    const content = await readFile(API_ENV_PATH, "utf8");
    const match = content.match(/^FINNHUB_API_KEY=(.*)$/m);
    const key = match?.[1]?.trim() ?? "";
    return NextResponse.json({
      configured: key.length > 0,
      masked: key ? `${key.slice(0, 4)}…${key.slice(-4)}` : null,
    });
  } catch {
    return NextResponse.json({ configured: false, masked: null });
  }
}

export async function POST(request: Request) {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "Disabled in production." }, { status: 403 });
  }

  const body = (await request.json()) as { apiKey?: string };
  const apiKey = body.apiKey?.trim();

  if (!apiKey || apiKey.length < 10) {
    return NextResponse.json({ error: "Enter a valid Finnhub API key." }, { status: 400 });
  }

  try {
    await updateFinnhubKey(apiKey);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Could not save key" },
      { status: 500 },
    );
  }

  return NextResponse.json({
    ok: true,
    message: "Finnhub key saved. Restart the backend, then click Refresh live options.",
  });
}

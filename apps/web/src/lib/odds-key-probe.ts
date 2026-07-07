import path from "path";
import { readFile } from "fs/promises";

const API_ENV_PATH = path.join(process.cwd(), "..", "api", ".env");
const ODDS_API_BASE = "https://api.the-odds-api.com/v4";

export interface OddsKeyProbeEntry {
  index: number;
  masked: string;
  remaining: number | null;
  used: number | null;
  exhausted: boolean;
  valid: boolean;
  error?: string;
}

export interface OddsKeyProbeResult {
  configured: boolean;
  key_count: number;
  keys: OddsKeyProbeEntry[];
  total_remaining: number | null;
  monthly_capacity: number;
  active_key_index: number | null;
  connected: boolean;
  error?: string;
}

function maskKey(key: string) {
  if (key.length <= 8) return "••••";
  return `${key.slice(0, 4)}…${key.slice(-4)}`;
}

function parseOddsKeys(raw: string): string[] {
  const seen: string[] = [];
  for (const part of raw.split(/[,\s]+/)) {
    const key = part.trim();
    if (key && !seen.includes(key)) seen.push(key);
  }
  return seen;
}

async function loadOddsKeys(): Promise<string[]> {
  const fromEnv = process.env.ODDS_API_KEY?.trim();
  if (fromEnv) {
    return parseOddsKeys(fromEnv);
  }
  try {
    const content = await readFile(API_ENV_PATH, "utf8");
    const match = content.match(/^ODDS_API_KEY=(.*)$/m);
    return parseOddsKeys(match?.[1] ?? "");
  } catch {
    return [];
  }
}

export async function probeOddsKeysFromEnv(): Promise<OddsKeyProbeResult> {
  const keys = await loadOddsKeys();

  if (!keys.length) {
    return {
      configured: false,
      key_count: 0,
      keys: [],
      total_remaining: null,
      monthly_capacity: 0,
      active_key_index: null,
      connected: false,
      error: process.env.VERCEL
        ? undefined
        : "No ODDS_API_KEY in env or apps/api/.env",
    };
  }

  const entries = await Promise.all(
    keys.map(async (key, idx) => {
      const entry: OddsKeyProbeEntry = {
        index: idx + 1,
        masked: maskKey(key),
        remaining: null,
        used: null,
        exhausted: false,
        valid: false,
      };
      try {
        const res = await fetch(`${ODDS_API_BASE}/sports?apiKey=${encodeURIComponent(key)}`, {
          cache: "no-store",
        });
        const remaining = res.headers.get("x-requests-remaining");
        const used = res.headers.get("x-requests-used");
        if (remaining != null) {
          const n = parseInt(remaining, 10);
          entry.remaining = Number.isNaN(n) ? null : n;
          entry.exhausted = n <= 0;
        }
        if (used != null) {
          const u = parseInt(used, 10);
          entry.used = Number.isNaN(u) ? null : u;
        }
        entry.valid = res.ok;
        if (!res.ok) {
          entry.error = `HTTP ${res.status}`;
        }
      } catch (err) {
        entry.error = err instanceof Error ? err.message : "Probe failed";
      }
      return entry;
    }),
  );

  const total = entries.reduce((sum, e) => sum + Math.max(0, e.remaining ?? 0), 0);
  const activeIndex = entries.findIndex((e) => e.valid && !e.exhausted);

  return {
    configured: true,
    key_count: keys.length,
    keys: entries,
    total_remaining: total,
    monthly_capacity: keys.length * 500,
    active_key_index: activeIndex >= 0 ? activeIndex : null,
    connected: entries.some((e) => e.valid && !e.exhausted),
  };
}

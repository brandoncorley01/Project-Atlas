/** US sports slate clock — always Eastern, independent of browser timezone. */

export const SPORTS_TZ = "America/New_York";
/** Sports "Today" rolls at 6:00 AM ET so West Coast nightcaps stay on Tonight. */
export const SPORTS_SLATE_ROLL_HOUR = 6;

export function easternDayKey(iso: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: SPORTS_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(typeof iso === "string" ? new Date(iso) : iso);
}

/**
 * Sports-day key rolling at 6am ET.
 * A 1:05 AM ET Tuesday tip still belongs to Monday's Today/Tonight slate.
 */
export function sportsSlateDayKey(iso: string | Date = new Date()): string {
  const instant = typeof iso === "string" ? new Date(iso) : iso;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: SPORTS_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "numeric",
    hour12: false,
  }).formatToParts(instant);
  const year = Number(parts.find((p) => p.type === "year")?.value);
  const month = Number(parts.find((p) => p.type === "month")?.value);
  const day = Number(parts.find((p) => p.type === "day")?.value);
  let hour = Number(parts.find((p) => p.type === "hour")?.value);
  // Some engines emit hour "24" for midnight.
  if (hour === 24) hour = 0;
  const utcNoon = new Date(Date.UTC(year, month - 1, day, 12, 0, 0));
  if (hour < SPORTS_SLATE_ROLL_HOUR) {
    utcNoon.setUTCDate(utcNoon.getUTCDate() - 1);
  }
  return easternDayKey(utcNoon);
}

/** Human label for the active Eastern calendar slate day (e.g. "Mon, Aug 31"). */
export function sportsTodayLabelET(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: SPORTS_TZ,
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(now);
}

/** Kickoff display for sports cards — always US/Eastern so Today (ET) matches the clock. */
export function formatSportsKickoffET(iso?: string | null): string {
  if (!iso) return "TBD";
  try {
    return new Date(iso).toLocaleString("en-US", {
      timeZone: SPORTS_TZ,
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return iso;
  }
}

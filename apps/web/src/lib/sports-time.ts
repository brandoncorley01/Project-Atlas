/** US sports slate clock — always Eastern, independent of browser timezone. */

export const SPORTS_TZ = "America/New_York";

export function easternDayKey(iso: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: SPORTS_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(typeof iso === "string" ? new Date(iso) : iso);
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

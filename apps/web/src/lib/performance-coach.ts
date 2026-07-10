export interface CoachInsight {
  narrative?: string;
  focus_areas?: string[];
  by_module?: Record<
    string,
    {
      narrative?: string;
      win_rate?: number | null;
      total_signals?: number;
      pending?: number;
    }
  >;
  source?: string;
}

interface CoachSummaryInput {
  days?: number;
  total_signals?: number;
  pending?: number;
  win_rate?: number | null;
  learning_notes?: string[];
  calibration?: { learning_notes?: string[] };
  by_module?: Record<
    string,
    {
      total_signals?: number;
      pending?: number;
      win_rate?: number | null;
      wins?: number;
      losses?: number;
    }
  >;
}

/** Client-side coach copy when the API is unavailable or still loading. */
export function buildClientCoachInsight(summary: CoachSummaryInput): CoachInsight {
  const total = summary.total_signals ?? 0;
  const pending = summary.pending ?? 0;

  let narrative: string;
  if (total === 0 && pending === 0) {
    narrative =
      "No picks tracked yet. Tap Register all past picks below, or save plays to your watchlist and grade them when they settle.";
  } else if (total < 3) {
    narrative =
      "Log a few more settled picks with Win or Loss so Atlas can spot where confidence matches reality. Sports picks can auto-grade when games finish.";
  } else {
    const parts = [`You've logged ${total} outcomes in the last 30 days.`];
    if (summary.win_rate != null) {
      parts.push(`Win rate is ${summary.win_rate}%.`);
    }
    const notes = summary.learning_notes ?? summary.calibration?.learning_notes ?? [];
    if (notes.length > 0) {
      parts.push(notes[0]);
    } else {
      parts.push("Keep grading picks consistently — calibration kicks in after 8 closed results.");
    }
    narrative = parts.join(" ");
  }

  const focus_areas: string[] = [];
  const byMod = summary.by_module ?? {};
  for (const [mod, data] of Object.entries(byMod)) {
    if (!data || typeof data !== "object") continue;
    if ((data.losses ?? 0) > (data.wins ?? 0) && (data.total_signals ?? 0) >= 2) {
      focus_areas.push(`Review ${mod} picks — losses outnumber wins recently.`);
    }
  }
  if (pending > 0) {
    focus_areas.push(`${pending} pick(s) still awaiting a grade — use Grade buttons per sector below.`);
  }
  if (focus_areas.length === 0) {
    focus_areas.push("Log outcomes within 24h of settlement for sharper learning.");
  }

  const by_module: CoachInsight["by_module"] = {};
  for (const [mod, data] of Object.entries(byMod)) {
    if (!data || typeof data !== "object") continue;
    const modTotal = data.total_signals ?? 0;
    const modPending = data.pending ?? 0;
    if (modTotal === 0 && modPending === 0) continue;
    const parts: string[] = [];
    if (modTotal > 0) {
      parts.push(`${modTotal} graded in the last 30 days.`);
      if (data.win_rate != null) parts.push(`Win rate ${data.win_rate}%.`);
    }
    if (modPending > 0) parts.push(`${modPending} awaiting grade.`);
    by_module[mod] = {
      narrative: parts.join(" "),
      win_rate: data.win_rate,
      total_signals: modTotal,
      pending: modPending,
    };
  }

  return {
    narrative,
    focus_areas: focus_areas.slice(0, 3),
    by_module,
    source: "template",
  };
}

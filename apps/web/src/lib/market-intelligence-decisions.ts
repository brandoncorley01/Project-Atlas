/** Decision helpers for Options / Market Intelligence pages. */

export type DecisionStanceId = "take" | "size_small" | "watch" | "pass" | "tighten" | "hold" | "neutral";

export interface DecisionStance {
  id: DecisionStanceId;
  label: string;
  detail: string;
}

export interface DecisionAction {
  label: string;
  reason: string;
  href?: string;
  tone?: "positive" | "warning" | "neutral" | "danger";
}

function num(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

/** Stance for a single options flow / low-premium card. */
export function stanceForOptionsCard(card: Record<string, unknown>): DecisionStance {
  const unusual = num(card.unusual_score ?? (card.score as { final_score?: number } | undefined)?.final_score);
  const confidence = num(card.atlas_confidence ?? (card.score as { confidence?: number } | undefined)?.confidence);
  const spread = num(card.bid_ask_spread_pct, 99);
  const liquidity = String(card.liquidity_grade ?? "").toUpperCase();
  const premium = num(card.current_premium, 99);
  const direction = String(card.direction ?? "uncertain");

  if (direction === "uncertain" || unusual < 55) {
    return {
      id: "pass",
      label: "Pass",
      detail: "Unusualness or direction is too weak to act on — leave it.",
    };
  }
  if (spread > 12 || (liquidity && liquidity > "C")) {
    return {
      id: "watch",
      label: "Watch",
      detail: "Activity is interesting but liquidity/spread is poor — do not chase fills.",
    };
  }
  if (unusual >= 75 && confidence >= 65 && spread <= 6 && (liquidity === "A" || liquidity === "B")) {
    return {
      id: premium <= 5 ? "take" : "size_small",
      label: premium <= 5 ? "Review for entry" : "Size small",
      detail:
        premium <= 5
          ? "Score, confidence, and liquidity clear the bar for a one-contract review."
          : "Quality setup but premium is elevated — size carefully if you take it.",
    };
  }
  if (unusual >= 65 && confidence >= 55) {
    return {
      id: "size_small",
      label: "Size small",
      detail: "Decent unusualness — paper or one-lot only until confirmation improves.",
    };
  }
  return {
    id: "watch",
    label: "Watch",
    detail: "Borderline print — keep on the watchlist, do not force a trade.",
  };
}

export function stanceToneClass(id: DecisionStanceId): string {
  if (id === "take") return "border-emerald-500/40 bg-emerald-500/15 text-emerald-100";
  if (id === "size_small") return "border-sky-500/40 bg-sky-500/15 text-sky-100";
  if (id === "watch" || id === "hold") return "border-amber-500/35 bg-amber-500/10 text-amber-100";
  if (id === "pass") return "border-rose-500/35 bg-rose-500/10 text-rose-100";
  if (id === "tighten") return "border-orange-500/40 bg-orange-500/15 text-orange-100";
  return "border-border bg-surface/60 text-muted";
}

/** Build Options Intelligence "Today" brief from loaded boards. */
export function buildOptionsTodayBrief(input: {
  flow: Record<string, unknown>[];
  smartMoney: Record<string, unknown>[];
  performance: Record<string, unknown> | null;
  usingFixture: boolean;
}): { stance: DecisionStance; actions: DecisionAction[]; topCards: Record<string, unknown>[] } {
  const ranked = [...input.flow].sort(
    (a, b) =>
      num(b.unusual_score ?? (b.score as { final_score?: number } | undefined)?.final_score) -
      num(a.unusual_score ?? (a.score as { final_score?: number } | undefined)?.final_score),
  );
  const topCards = ranked.slice(0, 3);
  const best = topCards[0];
  const bestStance = best ? stanceForOptionsCard(best) : null;

  const stance: DecisionStance = bestStance
    ? {
        id: bestStance.id,
        label: bestStance.id === "take" || bestStance.id === "size_small" ? "Flow is actionable" : "Stay selective",
        detail: best
          ? `Top print: ${String(best.ticker)} (${String(best.direction)}). ${bestStance.detail}`
          : bestStance.detail,
      }
    : {
        id: "neutral",
        label: "No flow yet",
        detail: "Wait for unusual activity to load, then rank by score × liquidity.",
      };

  const actions: DecisionAction[] = [];
  if (best && (bestStance?.id === "take" || bestStance?.id === "size_small")) {
    actions.push({
      label: `Review ${String(best.ticker)}`,
      reason: String(best.explanation ?? bestStance.detail),
      href: "#flow-board",
      tone: "positive",
    });
  }
  const affordable = ranked.find((c) => num(c.current_premium) <= 5 && stanceForOptionsCard(c).id !== "pass");
  if (affordable && affordable !== best) {
    actions.push({
      label: `Low-premium: ${String(affordable.ticker)}`,
      reason: `$${num(affordable.current_premium).toFixed(2)} premium with unusual score ${String(affordable.unusual_score)}.`,
      href: "?tab=low-premium",
      tone: "neutral",
    });
  }
  if (input.smartMoney[0]) {
    const sm = input.smartMoney[0];
    actions.push({
      label: `Watch ${String(sm.underlying)} concentration`,
      reason: String(sm.label ?? "Concentrated activity — not proof of smart money."),
      href: "?tab=smart-money",
      tone: "warning",
    });
  }
  const tracked = num((input.performance?.summary as { signals_tracked?: number } | undefined)?.signals_tracked);
  if (tracked === 0) {
    actions.push({
      label: "Grade outcomes later",
      reason: "No options-intel signals graded yet — log results so the board learns.",
      href: "?tab=performance",
      tone: "neutral",
    });
  }
  if (input.usingFixture) {
    actions.unshift({
      label: "Treat as preview",
      reason: "Simulated fixtures — use to learn the workflow until delayed/live provider is connected.",
      tone: "warning",
    });
  }

  return { stance, actions: actions.slice(0, 4), topCards };
}

/** Build Market Intelligence decision brief from weather + rotation + exits. */
export function buildMarketTodayBrief(input: {
  weather: Record<string, unknown> | null;
  rotation: Record<string, unknown>[];
  exits: Record<string, unknown>[];
  usingFixture: boolean;
}): { stance: DecisionStance; actions: DecisionAction[] } {
  const weather = input.weather;
  const details = (weather?.details as Record<string, unknown> | undefined) ?? {};
  const label = String(weather?.label ?? "Regime unknown");
  const risk = String(weather?.risk_level ?? "unknown");
  const strongest = Array.isArray(details.strongest_sectors) ? (details.strongest_sectors as string[]) : [];
  const avoid = Array.isArray(details.areas_to_avoid) ? (details.areas_to_avoid as string[]) : [];

  let stanceId: DecisionStanceId = "neutral";
  const lower = label.toLowerCase();
  if (lower.includes("bull")) stanceId = "take";
  else if (lower.includes("bear") || lower.includes("risk-off")) stanceId = "pass";
  else if (lower.includes("caution") || lower.includes("choppy")) stanceId = "watch";

  const stance: DecisionStance = {
    id: stanceId,
    label,
    detail: `Risk ${risk}. ${strongest.length ? `Lean ${strongest.join(", ")}.` : ""} ${
      avoid.length ? `Avoid or underweight ${avoid.join(", ")}.` : ""
    }`.trim(),
  };

  const actions: DecisionAction[] = [];
  if (input.usingFixture) {
    actions.push({
      label: "Preview mode",
      reason: "Simulated Market Weather — useful for layout, not for live risk decisions.",
      tone: "warning",
    });
  }
  for (const sector of strongest.slice(0, 2)) {
    actions.push({
      label: `Lean into ${sector}`,
      reason: "Weather + rotation favor this group — prefer related names on Options Intel.",
      href: "/options-intelligence",
      tone: "positive",
    });
  }
  for (const sector of avoid.slice(0, 1)) {
    actions.push({
      label: `De-emphasize ${sector}`,
      reason: "Weather flags this as an area to avoid until conditions improve.",
      href: "?tab=rotation",
      tone: "warning",
    });
  }
  for (const tile of input.exits.slice(0, 2)) {
    const urgency = num(tile.exit_urgency);
    actions.push({
      label: `${String(tile.action ?? "Review")} · ${String(tile.symbol)}`,
      reason: String(tile.primary_reason ?? `Exit urgency ${urgency}`).slice(0, 160),
      href: "?tab=exit",
      tone: urgency >= 70 ? "danger" : "warning",
    });
  }
  const leading = input.rotation.find((r) => String(r.classification).toLowerCase() === "leading");
  if (leading && !strongest.includes(String(leading.sector))) {
    actions.push({
      label: `Rotation leader: ${String(leading.sector)}`,
      reason: (Array.isArray(leading.evidence) ? (leading.evidence as string[]).join(" · ") : "Leading sector").slice(
        0,
        140,
      ),
      href: "?tab=rotation",
      tone: "neutral",
    });
  }

  if (actions.length === 0) {
    actions.push({
      label: "Open Market Weather",
      reason: "Start with regime context, then check exits and sector rotation.",
      href: "?tab=weather",
      tone: "neutral",
    });
  }

  return { stance, actions: actions.slice(0, 5) };
}

export function exitBand(urgency: number): string {
  if (urgency <= 20) return "Strong Hold";
  if (urgency <= 40) return "Hold";
  if (urgency <= 55) return "Monitor Closely";
  if (urgency <= 70) return "Tighten Risk";
  if (urgency <= 85) return "Scale Out";
  return "Exit Review";
}

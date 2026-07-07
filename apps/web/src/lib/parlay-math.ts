import type { SportsSignal } from "@/components/sports/SportsSignalCard";

export interface ParlayLegInput {
  id: string;
  sport: string;
  event_name: string;
  bet_type: string;
  selection: string;
  odds_american: number;
  odds_decimal?: number;
  confidence_score?: number;
  risk_score?: number;
  expected_value?: number;
  event_start?: string | null;
}

export interface CalculatedParlay {
  name: string;
  style: string;
  combined_odds_american: number;
  combined_odds_decimal: number;
  expected_value: number;
  confidence_score: number;
  risk_score: number;
  opportunity_score: number;
  correlation_warning: string | null;
  legs: Array<{
    leg_order: number;
    sport: string;
    event_name: string;
    bet_type: string;
    selection: string;
    odds_american: number;
    sports_signal_id: string;
    event_start?: string | null;
  }>;
}

function americanToDecimal(odds: number): number {
  if (odds > 0) return 1 + odds / 100;
  return 1 + 100 / Math.abs(odds);
}

export function decimalToAmerican(decimal: number): number {
  if (decimal <= 1) return -110;
  if (decimal >= 2) return Math.round((decimal - 1) * 100);
  return Math.round(-100 / (decimal - 1));
}

export function detectCorrelation(legs: ParlayLegInput[]): string | null {
  const events = legs.map((l) => l.event_name);
  if (new Set(events).size !== events.length) {
    return "Multiple legs reference the same event — outcomes are highly correlated.";
  }
  const sports = legs.map((l) => l.sport);
  if (new Set(sports).size !== sports.length) {
    const dupes = [...new Set(sports.filter((s, i) => sports.indexOf(s) !== i))];
    return `Multiple legs in ${dupes.join(", ")} — diversify across sports when possible.`;
  }
  return null;
}

export function legFromSignal(signal: SportsSignal): ParlayLegInput {
  return {
    id: signal.id,
    sport: signal.sport,
    event_name: signal.event_name,
    bet_type: signal.bet_type,
    selection: signal.selection,
    odds_american: signal.odds_american,
    odds_decimal: signal.odds_decimal,
    confidence_score: signal.confidence_score,
    risk_score: signal.risk_score,
    expected_value: signal.expected_value,
    event_start: signal.event_start,
  };
}

export function calculateParlayLocally(legs: ParlayLegInput[]): CalculatedParlay | null {
  if (legs.length < 2 || legs.length > 6) return null;

  const events = legs.map((l) => l.event_name);
  if (new Set(events).size !== events.length) return null;

  const combinedDecimal = legs.reduce(
    (acc, leg) => acc * (leg.odds_decimal ?? americanToDecimal(leg.odds_american)),
    1,
  );
  const combinedAmerican = decimalToAmerican(combinedDecimal);

  const confidences = legs.map((l) => l.confidence_score ?? 50);
  const risks = legs.map((l) => l.risk_score ?? 50);
  const evs = legs.map((l) => l.expected_value ?? 0);
  const n = legs.length;

  const confidence = Math.min(...confidences) * 0.85 + confidences.reduce((a, b) => a + b, 0) / n * 0.15;
  const risk = Math.min(92, risks.reduce((a, b) => a + b, 0) / n + (n - 2) * 6);
  const combinedEv = evs.reduce((a, b) => a + b, 0) / n;
  const opportunity = Math.min(
    95,
    confidence * 0.45 + (100 - risk) * 0.3 + combinedEv * 2.5 + n * 2,
  );

  const sports = [...new Set(legs.map((l) => l.sport))];
  const sportTag = sports
    .slice(0, 3)
    .map((s) => s.slice(0, 4))
    .join("+");
  const name = `Custom · ${n}-leg · ${sportTag}${sports.length > 3 ? `+${sports.length - 3}` : ""}`;

  const style = n === 2 ? "conservative" : n === 3 ? "balanced" : n === 4 ? "aggressive" : "custom";

  return {
    name,
    style,
    combined_odds_american: combinedAmerican,
    combined_odds_decimal: Math.round(combinedDecimal * 10000) / 10000,
    expected_value: Math.round(combinedEv * 100) / 100,
    confidence_score: Math.round(confidence * 10) / 10,
    risk_score: Math.round(risk * 10) / 10,
    opportunity_score: Math.round(opportunity * 10) / 10,
    correlation_warning: detectCorrelation(legs),
    legs: legs.map((leg, idx) => ({
      leg_order: idx + 1,
      sport: leg.sport,
      event_name: leg.event_name,
      bet_type: leg.bet_type,
      selection: leg.selection,
      odds_american: leg.odds_american,
      sports_signal_id: leg.id,
      event_start: leg.event_start,
    })),
  };
}

export function payoutFromStake(stake: number, decimalOdds: number): {
  totalReturn: number;
  profit: number;
} {
  const totalReturn = stake * decimalOdds;
  return {
    totalReturn: Math.round(totalReturn * 100) / 100,
    profit: Math.round((totalReturn - stake) * 100) / 100,
  };
}

export function formatParlayTicket(parlay: CalculatedParlay): string {
  const lines = parlay.legs.map(
    (leg) =>
      `Leg ${leg.leg_order}: ${leg.selection} (${leg.bet_type}) — ${leg.event_name} · ${leg.odds_american > 0 ? "+" : ""}${leg.odds_american}`,
  );
  lines.push(
    `Combined: ${parlay.combined_odds_american > 0 ? "+" : ""}${parlay.combined_odds_american} (${parlay.combined_odds_decimal.toFixed(2)}x)`,
  );
  return lines.join("\n");
}

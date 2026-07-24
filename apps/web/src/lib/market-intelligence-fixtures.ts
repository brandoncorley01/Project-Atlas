/** Client-side simulated fixtures so Options/Market Intelligence pages
 *  remain visible when the API branch is not deployed yet.
 *  Always labelled simulated — never presented as live.
 */

export const CLIENT_FIXTURE_FRESHNESS = {
  provider_name: "Atlas Client Fixture",
  data_timestamp: new Date().toISOString(),
  evaluation_timestamp: new Date().toISOString(),
  data_status: "simulated",
  data_freshness: "simulated_fresh",
  missing_fields: [] as string[],
};

export const CLIENT_FLOW_CARDS: Record<string, unknown>[] = [
  {
    ticker: "AAPL",
    contract: "AAPL 2026-08-21 210 CALL",
    direction: "bullish",
    strike: "210",
    expiration: "2026-08-21",
    current_premium: "3.45",
    estimated_total_premium: "293250",
    bid_ask_spread_pct: 2.9,
    volume: 4200,
    open_interest: 1800,
    volume_oi_ratio: "2.33",
    implied_volatility: "0.28",
    delta: "0.42",
    unusual_score: 78,
    atlas_confidence: 72,
    risk_level: "moderate",
    liquidity_grade: "A",
    explanation:
      "Bullish lean with unusual score 78/100. Ask-side call sweep with elevated volume/OI. Simulated fixture for preview.",
    warnings: ["Simulated data — not live options tape"],
    suggested_review_zone: { note: "Review zone only — not a guaranteed entry", premium_ref: "3.45" },
    data_status: "simulated",
    provider: "client_fixture",
    idempotency_key: "client-aapl-1",
    score: {
      score_version: "options_activity_v1",
      final_score: 78,
      confidence: 72,
      data_quality: "medium",
      positive_contributors: ["Volume/OI elevated", "Sweep classification"],
      negative_contributors: [],
      penalties: [],
    },
  },
  {
    ticker: "NVDA",
    contract: "NVDA 2026-08-15 120 PUT",
    direction: "bearish",
    strike: "120",
    expiration: "2026-08-15",
    current_premium: "1.85",
    estimated_total_premium: "222000",
    bid_ask_spread_pct: 8.1,
    volume: 5500,
    open_interest: 2200,
    volume_oi_ratio: "2.50",
    implied_volatility: "0.41",
    delta: "-0.38",
    unusual_score: 74,
    atlas_confidence: 61,
    risk_level: "moderate",
    liquidity_grade: "B",
    explanation:
      "Bearish lean (ask-side puts). Intent may still be hedge/spread — labelled carefully. Simulated fixture.",
    warnings: ["Open/close unknown", "Simulated data — not live options tape"],
    suggested_review_zone: { note: "Review zone only — not a guaranteed entry", premium_ref: "1.85" },
    data_status: "simulated",
    provider: "client_fixture",
    idempotency_key: "client-nvda-1",
    score: {
      score_version: "options_activity_v1",
      final_score: 74,
      confidence: 61,
      data_quality: "medium",
    },
  },
  {
    ticker: "SPY",
    contract: "SPY 2026-08-01 560 CALL",
    direction: "bullish",
    strike: "560",
    expiration: "2026-08-01",
    current_premium: "4.20",
    estimated_total_premium: "840000",
    bid_ask_spread_pct: 2.4,
    volume: 15000,
    open_interest: 8000,
    volume_oi_ratio: "1.88",
    delta: "0.48",
    unusual_score: 82,
    atlas_confidence: 70,
    risk_level: "contained",
    liquidity_grade: "A",
    explanation: "Index call sweep with strong liquidity. Simulated fixture for UI preview.",
    warnings: ["Simulated data — not live options tape"],
    suggested_review_zone: { note: "Review zone only — not a guaranteed entry", premium_ref: "4.20" },
    data_status: "simulated",
    provider: "client_fixture",
    idempotency_key: "client-spy-1",
    score: { score_version: "options_activity_v1", final_score: 82, confidence: 70, data_quality: "medium" },
  },
];

export const CLIENT_SMART_MONEY: Record<string, unknown>[] = [
  {
    underlying: "AAPL",
    label: "Concentrated bullish activity",
    event_count: 2,
    total_premium: 450000,
    unusual_score: 78,
    confidence: 72,
    directions: ["bullish"],
    evidence: [
      "Activity across 2 strikes",
      "2 related prints",
      "Combined premium ≈ $450,000",
      "Large size does not prove smart money or institutional identity",
    ],
    sector: "Technology",
    data_status: "simulated",
    disclaimer: "Atlas does not identify institutions. Concentrated activity may be hedges or spreads.",
  },
];

export const CLIENT_HEATMAP = {
  size_by: "market_cap",
  color_by: "options_bias",
  sectors: [
    {
      sector: "Technology",
      tiles: [
        { symbol: "AAPL", sector: "Technology", size_value: 450000, color_value: 0.8, label: "Up / constructive", options_bias: 0.8 },
        { symbol: "NVDA", sector: "Technology", size_value: 222000, color_value: -0.7, label: "Down / pressured", options_bias: -0.7 },
      ],
    },
    {
      sector: "Index",
      tiles: [
        { symbol: "SPY", sector: "Index", size_value: 840000, color_value: 0.6, label: "Up / constructive", options_bias: 0.6 },
      ],
    },
    {
      sector: "Energy",
      tiles: [
        { symbol: "XOM", sector: "Energy", size_value: 38000, color_value: 0.2, label: "Flat / mixed", options_bias: 0.2 },
      ],
    },
  ],
  table_fallback: [
    { symbol: "AAPL", sector: "Technology", label: "Up / constructive", options_bias: 0.8 },
    { symbol: "NVDA", sector: "Technology", label: "Down / pressured", options_bias: -0.7 },
    { symbol: "SPY", sector: "Index", label: "Up / constructive", options_bias: 0.6 },
    { symbol: "XOM", sector: "Energy", label: "Flat / mixed", options_bias: 0.2 },
  ],
  legend: {
    size: "qualifying premium",
    color: "options_bias",
    note: "Color encodes directional evidence; labels are color-independent.",
  },
  freshness: CLIENT_FIXTURE_FRESHNESS,
  disclaimer: "Simulated client heatmap for preview when API is unavailable.",
};

export const CLIENT_SECTOR_ROTATION = {
  items: [
    {
      sector: "Technology",
      classification: "Leading",
      relative_return: 1.8,
      options_bias: 0.4,
      member_count: 2,
      evidence: ["Relative return +1.80%", "Breadth above MA 63%", "Options bias +0.40"],
    },
    {
      sector: "Index",
      classification: "Strengthening",
      relative_return: 0.6,
      options_bias: 0.3,
      member_count: 1,
      evidence: ["Relative return +0.60%", "Options bias +0.30"],
    },
    {
      sector: "Energy",
      classification: "Mixed",
      relative_return: -0.2,
      options_bias: 0.1,
      member_count: 1,
      evidence: ["Relative return -0.20%", "Options bias +0.10"],
    },
  ],
  freshness: CLIENT_FIXTURE_FRESHNESS,
  disclaimer: "Simulated sector rotation for preview.",
};

export const CLIENT_WEATHER = {
  label: "Cautiously bullish",
  confidence: 62,
  risk_level: "moderate",
  last_update: new Date().toISOString(),
  details: {
    supporting_evidence: ["Options bias leans bullish", "Technology sector leading in fixture set"],
    main_risks: ["Simulated inputs only", "Volatility regime not live"],
    strongest_sectors: ["Technology", "Index"],
    areas_to_avoid: ["Energy"],
    disclaimer:
      "Market Weather describes recent conditions and regime context. It is not a literal forecast. This preview uses simulated fixtures.",
  },
  score: {
    score_key: "market_weather",
    score_version: "weather_v1",
    final_score: 58,
    confidence: 62,
    data_quality: "medium",
    component_values: { index: 58, breadth: 55, sectors: 60, options: 62, volatility: 55, news: 50 },
    weights: { index: 0.25, breadth: 0.2, sectors: 0.2, options: 0.15, volatility: 0.1, news: 0.1 },
    positive_contributors: ["Options bias leans bullish"],
    negative_contributors: ["Simulated inputs only"],
    missing_inputs: ["live_index_feed"],
    penalties: [],
  },
  freshness: CLIENT_FIXTURE_FRESHNESS,
};

export const CLIENT_EXIT_HEATMAP = {
  ...CLIENT_HEATMAP,
  color_by: "exit_urgency",
  tiles_detail: [
    {
      symbol: "AAPL",
      sector: "Technology",
      exit_urgency: 58,
      action: "Tighten Stop",
      thesis_status: "intact",
      confidence: 64,
      primary_reason:
        "Tighten Stop. Urgency band: Tighten Risk. Supporting: Still above primary trend level. Watch: Options flow turning against position. This is decision support, not an order instruction.",
      main_risk: "Options flow turning against position",
      daily_return: 18,
    },
  ],
  table_fallback: [
    {
      symbol: "AAPL",
      sector: "Technology",
      label: "Elevated",
      exit_urgency: 58,
      action: "Tighten Stop",
    },
  ],
  freshness: CLIENT_FIXTURE_FRESHNESS,
  disclaimer: "Simulated exit heatmap — watchlist proxy until API/ledger is live.",
};

export const CLIENT_ALERTS = {
  items: [
    { alert_type: "unusual_options_signal", enabled: true, threshold: 70, cooldown_minutes: 60 },
    { alert_type: "low_premium_opportunity", enabled: false, threshold: 70, cooldown_minutes: 60 },
    { alert_type: "exit_urgency_threshold", enabled: true, threshold: 70, cooldown_minutes: 60 },
    { alert_type: "market_weather_change", enabled: true, threshold: null, cooldown_minutes: 60 },
  ],
  allow_simulated_alerts: true,
};

export const CLIENT_PERFORMANCE = {
  summary: {
    signals_tracked: 0,
    note: "Preview mode — connect API + migration for live outcome tracking.",
  },
  disclaimer: "Example methodology only — not a live performance claim.",
};

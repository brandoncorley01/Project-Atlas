/** Client-side decision fixtures for Market / Options Intelligence.
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
      "Ask-side call activity with elevated volume vs open interest. Worth a closer look if your bullish thesis on AAPL already exists — not a standalone buy signal.",
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
      positive_contributors: ["Volume/OI elevated", "Sweep classification", "Tight spread"],
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
      "Ask-side put activity looks defensive, but large put prints can be hedges. Treat direction as uncertain until price action confirms.",
    warnings: ["Open/close unknown", "Possible hedge", "Simulated data — not live options tape"],
    suggested_review_zone: { note: "Review zone only — not a guaranteed entry", premium_ref: "1.85" },
    data_status: "simulated",
    provider: "client_fixture",
    idempotency_key: "client-nvda-1",
    score: {
      score_version: "options_activity_v1",
      final_score: 74,
      confidence: 61,
      data_quality: "medium",
      positive_contributors: ["Elevated notional", "Block-sized print"],
      negative_contributors: ["Wider spread", "Intent uncertain"],
      penalties: [],
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
    explanation:
      "Liquid index call activity supports a constructive near-term tape. Useful as market-regime confirmation more than a single-name trade.",
    warnings: ["Simulated data — not live options tape"],
    suggested_review_zone: { note: "Review zone only — not a guaranteed entry", premium_ref: "4.20" },
    data_status: "simulated",
    provider: "client_fixture",
    idempotency_key: "client-spy-1",
    score: {
      score_version: "options_activity_v1",
      final_score: 82,
      confidence: 70,
      data_quality: "medium",
      positive_contributors: ["High liquidity", "Elevated volume/OI"],
      negative_contributors: [],
      penalties: [],
    },
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
      "Repeated call activity across 2 strikes",
      "Combined premium ≈ $450,000",
      "Liquidity is usable (tight spreads on listed prints)",
    ],
    takeaway: "Multiple bullish-leaning prints on the same name — review only if your stock thesis already aligns.",
    sector: "Technology",
    data_status: "simulated",
    disclaimer: "Atlas does not identify institutions. Concentrated activity may be hedges or spreads.",
  },
];

export const CLIENT_HEATMAP = {
  size_by: "market_cap",
  color_by: "options_bias",
  meaning:
    "Larger tiles = more options premium in focus. Constructive tiles lean bullish; pressured tiles lean bearish or defensive.",
  sectors: [
    {
      sector: "Technology",
      tiles: [
        {
          symbol: "AAPL",
          sector: "Technology",
          size_value: 450000,
          color_value: 0.8,
          label: "Constructive",
          options_bias: 0.8,
          takeaway: "Call-side activity is concentrated — confirm with price holding support.",
        },
        {
          symbol: "NVDA",
          sector: "Technology",
          size_value: 222000,
          color_value: -0.7,
          label: "Pressured",
          options_bias: -0.7,
          takeaway: "Put activity elevated — could be hedge. Wait for confirmation before fading.",
        },
      ],
    },
    {
      sector: "Index",
      tiles: [
        {
          symbol: "SPY",
          sector: "Index",
          size_value: 840000,
          color_value: 0.6,
          label: "Constructive",
          options_bias: 0.6,
          takeaway: "Broad-market call bias supports risk-on swings — size carefully.",
        },
      ],
    },
    {
      sector: "Energy",
      tiles: [
        {
          symbol: "XOM",
          sector: "Energy",
          size_value: 38000,
          color_value: 0.2,
          label: "Mixed",
          options_bias: 0.2,
          takeaway: "No clear directional edge — skip unless you have a separate catalyst.",
        },
      ],
    },
  ],
  table_fallback: [
    { symbol: "AAPL", sector: "Technology", label: "Constructive", options_bias: 0.8, takeaway: "Call-side concentration" },
    { symbol: "NVDA", sector: "Technology", label: "Pressured", options_bias: -0.7, takeaway: "Put activity / possible hedge" },
    { symbol: "SPY", sector: "Index", label: "Constructive", options_bias: 0.6, takeaway: "Risk-on confirmation" },
    { symbol: "XOM", sector: "Energy", label: "Mixed", options_bias: 0.2, takeaway: "No clear edge" },
  ],
  legend: {
    size: "options premium in focus",
    color: "directional lean",
    note: "Labels are color-independent. This is evidence context, not a forecast.",
  },
  freshness: CLIENT_FIXTURE_FRESHNESS,
  disclaimer: "Simulated heatmap for decision-preview when API is unavailable.",
};

export const CLIENT_SECTOR_ROTATION = {
  items: [
    {
      sector: "Technology",
      classification: "Leading",
      relative_return: 1.8,
      options_bias: 0.4,
      member_count: 2,
      posture: "Favor relative strength",
      guidance: "Prefer long ideas here over lagging groups while leadership holds.",
      evidence: ["Outperforming the tape", "Options bias constructive", "Breadth supportive"],
    },
    {
      sector: "Index",
      classification: "Strengthening",
      relative_return: 0.6,
      options_bias: 0.3,
      member_count: 1,
      posture: "Constructive backdrop",
      guidance: "Index call bias helps bullish swing setups — still respect volatility.",
      evidence: ["Positive relative return", "Options bias mildly bullish"],
    },
    {
      sector: "Energy",
      classification: "Mixed",
      relative_return: -0.2,
      options_bias: 0.1,
      member_count: 1,
      posture: "Stand aside",
      guidance: "No clean leadership signal — avoid forcing new swing entries here.",
      evidence: ["Flat-to-soft relative return", "Weak directional options lean"],
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
  takeaway:
    "Backdrop supports selective long swings in leading sectors, but keep size modest and exits planned — conviction is not high enough for aggressive adds.",
  posture: "Selective risk-on",
  do_now: [
    "Favor Technology / broad-market strength over lagging groups",
    "Only take setups with clear invalidation",
    "Tighten risk on names where options flow turns against you",
  ],
  avoid_now: [
    "Chasing weak sectors without a catalyst",
    "Oversizing short-dated options in mixed names",
  ],
  details: {
    supporting_evidence: [
      "Options bias leans bullish on liquid names",
      "Technology is leading on relative strength",
    ],
    main_risks: [
      "Confidence is only moderate",
      "Some put activity may be hedging, not outright bearish conviction",
      "Data may be delayed or simulated",
    ],
    strongest_sectors: ["Technology", "Index"],
    areas_to_avoid: ["Energy"],
    favorable_environments: ["Pullback buys in leaders", "Continuation swings with sector confirmation"],
    disclaimer:
      "Market Weather describes recent conditions. It is decision support — not a forecast and not a guarantee.",
  },
  score: {
    score_key: "market_weather",
    score_version: "weather_v1",
    final_score: 58,
    confidence: 62,
    data_quality: "medium",
    component_values: { index: 58, breadth: 55, sectors: 60, options: 62, volatility: 55, news: 50 },
    weights: { index: 0.25, breadth: 0.2, sectors: 0.2, options: 0.15, volatility: 0.1, news: 0.1 },
    positive_contributors: ["Options bias leans bullish", "Sector leadership present"],
    negative_contributors: ["Only moderate confidence", "Incomplete live feeds"],
    missing_inputs: ["live_index_feed"],
    penalties: [],
  },
  freshness: CLIENT_FIXTURE_FRESHNESS,
};

export const CLIENT_EXIT_HEATMAP = {
  ...CLIENT_HEATMAP,
  color_by: "exit_urgency",
  meaning: "Higher exit urgency means review risk sooner — not an automatic sell order.",
  tiles_detail: [
    {
      symbol: "AAPL",
      sector: "Technology",
      exit_urgency: 58,
      urgency_band: "Tighten Risk",
      action: "Tighten Stop",
      thesis_status: "intact",
      confidence: 64,
      primary_reason:
        "Trend is still intact and the sector is leading, but call support has cooled near resistance — tighten the stop and protect gains.",
      main_risk: "Options flow turning against the position",
      supporting: ["Above primary trend level", "Sector still leading"],
      watching: ["Options support fading", "Momentum flattening"],
      daily_return: 18,
      takeaway: "Hold the core, but don’t give back the swing — trail risk tighter.",
    },
  ],
  table_fallback: [
    {
      symbol: "AAPL",
      sector: "Technology",
      label: "Tighten risk",
      exit_urgency: 58,
      action: "Tighten Stop",
      takeaway: "Protect gains while thesis remains intact",
    },
  ],
  freshness: CLIENT_FIXTURE_FRESHNESS,
  disclaimer: "Simulated exit guidance — decision support only.",
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
    note: "Outcome tracking fills in after signals persist and settle.",
  },
  disclaimer: "Methodological placeholder — not a live performance claim.",
};

export const SIGNAL_LABELS: Record<string, { name: string; description: string }> = {
  rsi: {
    name: "RSI",
    description: "Relative Strength Index — measures momentum. Below 30 = oversold (bullish), above 70 = overbought (bearish).",
  },
  macd: {
    name: "MACD",
    description: "Moving Average Convergence Divergence — trend momentum. Bullish when histogram is positive and rising.",
  },
  moving_averages: {
    name: "Moving Averages",
    description: "Price vs 20 EMA, 50 SMA, 200 SMA. Above all = bullish trend. Alignment bonus when 20 > 50 > 200.",
  },
  volume: {
    name: "Volume",
    description: "Relative Volume (RVOL) — compares today's volume to 20-day average. 1.5x+ confirms breakouts.",
  },
  breakout: {
    name: "Breakout",
    description: "Multi-timeframe breakout detection (20d, 55d, 252d highs/lows). Volume-confirmed breakouts score highest.",
  },
  gap: {
    name: "Gap",
    description: "Opening gap vs prior close, normalized by ATR. Large idiosyncratic gaps are significant.",
  },
  adx: {
    name: "Trend (ADX)",
    description: "Average Directional Index — measures trend strength. Above 25 = solid trend. Direction from +DI/-DI.",
  },
  earnings: {
    name: "Earnings",
    description: "Earnings proximity risk flag. Negative score inside 3-day blackout window. Not a directional signal.",
  },
  sec_filing: {
    name: "SEC Filings",
    description: "8-K event importance, insider buying (Form 4), 13D/13G stakes. Half-life decay on older filings.",
  },
  news_sentiment: {
    name: "News Sentiment",
    description: "LLM-classified news headlines — event type detection (earnings, M&A, guidance, etc.).",
  },
  relative_strength: {
    name: "Relative Strength",
    description: "Excess return vs SPY (20d/60d) and vs sector ETF (20d). Percentile-ranked across the S&P 500.",
  },
  pead: {
    name: "Post-Earnings Drift",
    description: "EPS/revenue surprise z-scores + day-1 tape confirmation. Active 1-30 days after earnings report.",
  },
};

export function getSignalLabel(key: string): string {
  return SIGNAL_LABELS[key]?.name ?? key;
}

export function getSignalDescription(key: string): string {
  return SIGNAL_LABELS[key]?.description ?? "";
}

export const THRESHOLD_LABELS: Record<string, { name: string; description: string }> = {
  buy: { name: "BUY Threshold", description: "Composite score >= this for a BUY signal" },
  watchlist: { name: "WATCHLIST Threshold", description: "Score >= this for WATCHLIST" },
  watchlist_relaxed: { name: "WATCHLIST (Relaxed)", description: "Lower threshold when trend + RS confirm" },
  caution: { name: "CAUTION Threshold", description: "Score <= this flags CAUTION for held positions" },
  sell: { name: "SELL Threshold", description: "Score <= this for SELL signal" },
  exit: { name: "Exit Threshold", description: "Score below this triggers exit" },
  confidence_min: { name: "Min Confidence", description: "Minimum confidence to trigger alerts" },
};

export const RISK_LABELS: Record<string, { name: string; description: string }> = {
  max_position_pct: { name: "Max Position %", description: "Max portfolio allocation per position" },
  max_sector_pct: { name: "Max Sector %", description: "Max allocation per sector" },
  risk_per_trade_pct: { name: "Risk Per Trade %", description: "Max risk per trade (ATR-based)" },
  max_positions: { name: "Max Positions", description: "Max simultaneous positions" },
  drawdown_half: { name: "Drawdown Half %", description: "At this drawdown, halve position sizes" },
  drawdown_pause: { name: "Drawdown Pause %", description: "At this drawdown, pause all new buys" },
  earnings_blackout_days: { name: "Earnings Blackout", description: "No new entries within this many days of earnings" },
};

export function getThresholdLabel(key: string): string {
  return THRESHOLD_LABELS[key]?.name ?? key.replace(/_/g, " ");
}
export function getThresholdDescription(key: string): string {
  return THRESHOLD_LABELS[key]?.description ?? "";
}
export function getRiskLabel(key: string): string {
  return RISK_LABELS[key]?.name ?? key.replace(/_/g, " ");
}
export function getRiskDescription(key: string): string {
  return RISK_LABELS[key]?.description ?? "";
}

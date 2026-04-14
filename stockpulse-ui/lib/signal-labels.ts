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

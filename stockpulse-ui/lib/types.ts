export interface Signal {
  score: number;
  weight: number;
  value: number | null;
}

export interface Bucket {
  avg_score: number;
  confirms: boolean;
}

export interface Confirmation {
  confirming_count: number;
  required: number;
  total_buckets: number;
  passes: boolean;
  buckets: Record<string, Bucket>;
}

export interface Risk {
  allowed: boolean;
  reasons: string[];
  size_multiplier: number;
  sector: string;
  industry: string;
  cluster_tickers: string[];
}

export interface Recommendation {
  ticker: string;
  timestamp: string;
  action: "BUY" | "WATCHLIST" | "HOLD" | "CAUTION" | "SELL";
  confidence: number;
  composite_score: number;
  thesis: string;
  technical_summary: string;
  catalyst_summary: string;
  invalidation: string;
  signals: Record<string, Signal>;
  confirmation: Confirmation;
  risk: Risk;
  high_conviction: boolean;
  position_caution: boolean;
  source?: "user" | "discovered";
}

export interface Position {
  ticker: string;
  shares: number;
  entry_price: number;
  entry_date: string;
  current_price: number;
  invested: number;
  current_value: number;
  pnl: number;
  pnl_pct: number;
}

export interface Portfolio {
  timestamp: string;
  total_invested: number;
  total_current: number;
  total_pnl: number;
  total_pnl_pct: number;
  positions: Position[];
  drawdown?: { drawdown_pct: number; size_multiplier: number; new_buys_paused: boolean };
}

export interface ScanStatus {
  running: boolean;
  progress: string;
  last_completed: string;
  next_scheduled: string;
}

export interface Activity {
  timestamp: string;
  type: string;
  message: string;
}

export interface Report {
  filename: string;
  date: string;
  type: string;
  title: string;
}

export interface Alert {
  timestamp: string;
  ticker: string;
  action: string;
  confidence: number;
  thesis: string;
  type: string;
}

export type Action = "BUY" | "WATCHLIST" | "HOLD" | "CAUTION" | "SELL";

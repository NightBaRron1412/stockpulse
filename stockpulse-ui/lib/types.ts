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

export interface AdvisorSuggestion {
  severity: "urgent" | "actionable" | "info";
  suggestion_type: string;
  ticker: string;
  action: string;
  summary: string;
  details: string;
  score: number;
  confidence: number;
  hash: string;
  suggested_amount?: number;
  trim_fraction?: number;
  swap_out_ticker?: string;
  swap_out_score?: number;
  swap_score_gap?: number;
  tax_impact_note?: string;
  wash_sale_warning: boolean;
  persistence_count: number;
  is_new: boolean;
  entry_timing?: { timing: "now" | "wait" | "limit"; reason: string; target_price?: number; confidence: number };
  pattern_match?: { match_count: number; avg_return_5d: number; avg_return_10d: number; avg_return_20d: number; win_rate: number; best_case: string; worst_case: string };
  regime?: string;
}

export interface MarketRegime {
  regime: "trending" | "ranging" | "correcting" | "selling_off";
  spy_price: number;
  spy_ema20: number;
  spy_sma50: number;
  spy_sma200: number;
  spy_adx: number;
  spy_rsi: number;
  spy_drawdown_pct: number;
  vix_level: number;
  confidence: number;
}

export interface AdvisorResponse {
  suggestions: AdvisorSuggestion[];
  last_run: string | null;
  scan_trigger: string | null;
  regime?: MarketRegime;
}

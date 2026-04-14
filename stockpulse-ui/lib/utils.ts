import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function actionColor(action: string): string {
  const colors: Record<string, string> = {
    BUY: "text-green-400",
    WATCHLIST: "text-blue-400",
    HOLD: "text-slate-400",
    CAUTION: "text-orange-400",
    SELL: "text-red-400",
  };
  return colors[action] || "text-slate-400";
}

export function actionBadgeClass(action: string): string {
  const classes: Record<string, string> = {
    BUY: "badge-buy",
    WATCHLIST: "badge-watchlist",
    HOLD: "badge-hold",
    CAUTION: "badge-caution",
    SELL: "badge-sell",
  };
  return classes[action] || "badge-hold";
}

export function formatPnl(value: number): string {
  return `${value >= 0 ? "+" : ""}$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function formatScore(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

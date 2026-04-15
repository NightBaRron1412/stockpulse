"use client";

import { useState } from "react";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { TickerLink } from "@/components/ticker-link";
import { Button } from "@/components/ui/button";
import type { AdvisorResponse, AdvisorSuggestion } from "@/lib/types";

const SEVERITY_CONFIG = {
  urgent: {
    label: "Urgent",
    border: "border-red-500/50",
    bg: "bg-red-500/5",
    badge: "bg-red-500/15 text-red-400 border-red-500/30",
    icon: "\uD83D\uDEA8",
  },
  actionable: {
    label: "Actionable",
    border: "border-amber-500/50",
    bg: "bg-amber-500/5",
    badge: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    icon: "\uD83D\uDCCB",
  },
  info: {
    label: "Informational",
    border: "border-blue-500/50",
    bg: "bg-blue-500/5",
    badge: "bg-blue-500/15 text-blue-400 border-blue-500/30",
    icon: "\u2139\uFE0F",
  },
};

function SuggestionCard({ suggestion, onDismiss }: { suggestion: AdvisorSuggestion; onDismiss: (hash: string) => void }) {
  const sev = SEVERITY_CONFIG[suggestion.severity] || SEVERITY_CONFIG.info;

  return (
    <div className={cn("glass-card p-5 border-l-4 space-y-3", sev.border, sev.bg)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn("px-2 py-0.5 rounded text-[11px] font-medium border", sev.badge)}>
            {sev.icon} {sev.label}
          </span>
          <TickerLink ticker={suggestion.ticker} />
          <span className="text-xs text-slate-400 font-mono-data">
            {suggestion.action}
          </span>
          {suggestion.is_new && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-500/15 text-green-400 border border-green-500/25">
              NEW
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDismiss(suggestion.hash)}
          className="text-slate-500 hover:text-slate-300 text-xs shrink-0"
        >
          Dismiss
        </Button>
      </div>

      <p className="text-sm text-slate-200 font-medium">{suggestion.summary}</p>

      {suggestion.details && (
        <p className="text-xs text-slate-400 leading-relaxed">{suggestion.details}</p>
      )}

      <div className="flex flex-wrap gap-3 text-xs text-slate-500">
        {suggestion.score !== 0 && (
          <span className="font-mono-data">
            Score: <span className={suggestion.score >= 0 ? "text-green-400" : "text-red-400"}>
              {suggestion.score >= 0 ? "+" : ""}{suggestion.score.toFixed(1)}
            </span>
          </span>
        )}
        {suggestion.suggested_amount != null && (
          <span className="font-mono-data">
            Amount: <span className="text-slate-300">${suggestion.suggested_amount.toLocaleString("en-US", { minimumFractionDigits: 0 })}</span>
          </span>
        )}
        {suggestion.swap_out_ticker && (
          <span>
            Swap: <span className="text-red-400">{suggestion.swap_out_ticker}</span> ({suggestion.swap_out_score?.toFixed(1)})
            {" "}&rarr;{" "}
            <span className="text-green-400">{suggestion.ticker}</span>
            {suggestion.swap_score_gap != null && (
              <span className="text-slate-400"> (gap: +{suggestion.swap_score_gap.toFixed(1)})</span>
            )}
          </span>
        )}
        {suggestion.trim_fraction != null && (
          <span className="font-mono-data">
            Trim: {(suggestion.trim_fraction * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {(suggestion.tax_impact_note || suggestion.wash_sale_warning) && (
        <div className="flex flex-wrap gap-2 pt-1">
          {suggestion.tax_impact_note && (
            <span className="px-2 py-0.5 rounded text-[10px] bg-slate-700/50 text-slate-400">
              {suggestion.tax_impact_note}
            </span>
          )}
          {suggestion.wash_sale_warning && (
            <span className="px-2 py-0.5 rounded text-[10px] bg-red-500/15 text-red-400 border border-red-500/25">
              WASH SALE WARNING
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default function AdvisorPage() {
  const { data, loading, refresh } = usePolling<AdvisorResponse>(api.advisorSuggestions, 30000);
  const [evaluating, setEvaluating] = useState(false);
  const [dismissing, setDismissing] = useState<string | null>(null);

  async function handleEvaluate() {
    setEvaluating(true);
    try {
      await api.advisorEvaluate();
      // Poll every 2s until results update or 30s timeout
      const startTime = Date.now();
      const prevRun = data?.last_run;
      const poll = setInterval(async () => {
        try {
          const result = await api.advisorSuggestions();
          if (result.last_run !== prevRun || Date.now() - startTime > 30000) {
            clearInterval(poll);
            refresh();
            setEvaluating(false);
          }
        } catch {
          clearInterval(poll);
          setEvaluating(false);
        }
      }, 2000);
    } catch {
      setEvaluating(false);
    }
  }

  async function handleDismiss(hash: string) {
    setDismissing(hash);
    try {
      await api.advisorAcknowledge(hash);
      refresh();
    } finally {
      setDismissing(null);
    }
  }

  const suggestions = data?.suggestions ?? [];
  const urgent = suggestions.filter((s) => s.severity === "urgent");
  const actionable = suggestions.filter((s) => s.severity === "actionable");
  const info = suggestions.filter((s) => s.severity === "info");

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Portfolio Advisor</h1>
          {data?.last_run && (
            <p className="text-xs text-slate-500 mt-1">
              Last evaluated: {new Date(data.last_run).toLocaleString()} ({data.scan_trigger})
            </p>
          )}
        </div>
        <Button
          onClick={handleEvaluate}
          disabled={evaluating}
          className="bg-blue-600 hover:bg-blue-500 text-white font-medium px-5"
        >
          {evaluating ? (
            <span className="flex items-center gap-2">
              <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Evaluating...
            </span>
          ) : (
            "Evaluate Now"
          )}
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className={cn("glass-card p-4 border-l-4", urgent.length > 0 ? "border-red-500/60" : "border-slate-700/30")}>
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Urgent</p>
          <p className={cn("text-2xl font-bold font-mono-data", urgent.length > 0 ? "text-red-400" : "text-slate-600")}>
            {urgent.length}
          </p>
        </div>
        <div className={cn("glass-card p-4 border-l-4", actionable.length > 0 ? "border-amber-500/60" : "border-slate-700/30")}>
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Actionable</p>
          <p className={cn("text-2xl font-bold font-mono-data", actionable.length > 0 ? "text-amber-400" : "text-slate-600")}>
            {actionable.length}
          </p>
        </div>
        <div className={cn("glass-card p-4 border-l-4", info.length > 0 ? "border-blue-500/60" : "border-slate-700/30")}>
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Informational</p>
          <p className={cn("text-2xl font-bold font-mono-data", info.length > 0 ? "text-blue-400" : "text-slate-600")}>
            {info.length}
          </p>
        </div>
      </div>

      {loading && suggestions.length === 0 && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="glass-card p-6 animate-pulse space-y-3">
              <div className="h-4 bg-slate-700/50 rounded w-40" />
              <div className="h-6 bg-slate-700/50 rounded w-full" />
              <div className="h-4 bg-slate-700/50 rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {/* Urgent */}
      {urgent.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-red-400 uppercase tracking-wider">Urgent Actions</h2>
          {urgent.map((s) => (
            <SuggestionCard key={s.hash} suggestion={s} onDismiss={handleDismiss} />
          ))}
        </div>
      )}

      {/* Actionable */}
      {actionable.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-amber-400 uppercase tracking-wider">Actionable</h2>
          {actionable.map((s) => (
            <SuggestionCard key={s.hash} suggestion={s} onDismiss={handleDismiss} />
          ))}
        </div>
      )}

      {/* Informational */}
      {info.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-blue-400 uppercase tracking-wider">Informational</h2>
          {info.map((s) => (
            <SuggestionCard key={s.hash} suggestion={s} onDismiss={handleDismiss} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && suggestions.length === 0 && (
        <div className="glass-card p-12 text-center">
          <p className="text-lg text-slate-400 mb-2">No suggestions</p>
          <p className="text-sm text-slate-500">
            Portfolio looks good. The advisor will generate suggestions after the next scan.
          </p>
        </div>
      )}
    </div>
  );
}

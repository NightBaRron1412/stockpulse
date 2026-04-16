"use client";

import { useState } from "react";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ReboundPage() {
  const { data: status, refresh: refreshStatus } = usePolling<any>(api.reboundStatus, 30000);
  const { data: exits } = usePolling<any[]>(api.reboundExits, 15000);
  const [scanning, setScanning] = useState(false);
  const [candidates, setCandidates] = useState<any[]>([]);
  const [closing, setClosing] = useState<string | null>(null);
  const [closePrice, setClosePrice] = useState("");
  const [editingSleeve, setEditingSleeve] = useState(false);
  const [sleeveInput, setSleeveInput] = useState("");
  const [cashInput, setCashInput] = useState("");

  const [activeDips, setActiveDips] = useState<any[]>([]);

  async function handleScan() {
    setScanning(true);
    try {
      const result = await api.reboundScan();
      setCandidates(result.candidates || []);
      setActiveDips(result.active_dips || []);
    } finally {
      setScanning(false);
    }
  }

  async function handleOpen(candidate: any) {
    const price = prompt(`Entry price for ${candidate.ticker}:`, String(candidate.current_price));
    if (!price) return;
    try {
      await api.reboundOpen({
        ticker: candidate.ticker,
        shares: candidate.suggested_shares,
        entry_price: parseFloat(price),
        stop_price: candidate.stop_price,
        target_price: candidate.target_price,
        setup: candidate.setup,
      });
      refreshStatus();
      setCandidates(prev => prev.filter(c => c.ticker !== candidate.ticker));
    } catch (e: any) {
      alert(`Failed: ${e.message}`);
    }
  }

  async function handleClose(ticker: string) {
    const price = closePrice || prompt(`Exit price for ${ticker}:`);
    if (!price) return;
    try {
      await api.reboundClose(ticker, parseFloat(price));
      refreshStatus();
      setClosing(null);
      setClosePrice("");
    } catch (e: any) {
      alert(`Failed: ${e.message}`);
    }
  }

  const activeTrades = status?.active_trades ?? [];
  const exitAlerts = exits ?? [];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Rebound-2D</h1>
          <p className="text-xs text-slate-500 mt-1">Intraday dip-buy sleeve | 1-2 day hold | Manual execution</p>
        </div>
        <Button onClick={handleScan} disabled={scanning}
          className="bg-blue-600 hover:bg-blue-500 text-white font-medium px-5">
          {scanning ? "Scanning..." : "Scan for Setups"}
        </Button>
      </div>

      {/* Sleeve Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4">
        <div className="glass-card p-4">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Sleeve</p>
          <p className="text-xl font-bold font-mono-data text-slate-200">${status?.sleeve_size?.toLocaleString() ?? "2,000"}</p>
          {!editingSleeve && (
            <button onClick={() => { setEditingSleeve(true); setSleeveInput(String(status?.sleeve_size ?? 2000)); setCashInput(String(status?.cash ?? 2000)); }}
              className="text-[10px] text-blue-400 hover:text-blue-300 mt-1">Edit</button>
          )}
        </div>
        <div className="glass-card p-4">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Cash</p>
          <p className="text-xl font-bold font-mono-data text-green-400">${status?.cash?.toLocaleString() ?? "2,000"}</p>
          {editingSleeve && (
            <div className="flex flex-col gap-1.5 mt-2">
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-slate-500 w-10">Sleeve</span>
                <Input type="number" step={100} value={sleeveInput} onChange={(e) => setSleeveInput(e.target.value)}
                  className="h-6 text-[10px] bg-slate-800/50 border-slate-700/50 w-20 font-mono-data" />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-slate-500 w-10">Cash</span>
                <Input type="number" step={100} value={cashInput} onChange={(e) => setCashInput(e.target.value)}
                  className="h-6 text-[10px] bg-slate-800/50 border-slate-700/50 w-20 font-mono-data" />
              </div>
              <div className="flex gap-1">
                <Button size="sm" className="h-5 text-[10px] px-2 bg-blue-600" onClick={async () => {
                  await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000"}/api/rebound/cash`, {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ sleeve_size: parseFloat(sleeveInput), cash: parseFloat(cashInput) }),
                  });
                  setEditingSleeve(false);
                  refreshStatus();
                }}>Save</Button>
                <Button variant="ghost" size="sm" className="h-5 text-[10px] px-1" onClick={() => setEditingSleeve(false)}>X</Button>
              </div>
            </div>
          )}
        </div>
        <div className="glass-card p-4">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Active</p>
          <p className="text-xl font-bold font-mono-data text-blue-400">{status?.active_count ?? 0}</p>
        </div>
        <div className="glass-card p-4">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Win Rate</p>
          <p className={cn("text-xl font-bold font-mono-data", (status?.win_rate ?? 0) >= 50 ? "text-green-400" : "text-red-400")}>
            {status?.win_rate ?? 0}%
          </p>
        </div>
        <div className="glass-card p-4">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Total P&L</p>
          <p className={cn("text-xl font-bold font-mono-data", (status?.total_pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400")}>
            ${status?.total_pnl?.toFixed(2) ?? "0.00"}
          </p>
        </div>
        <div className="glass-card p-4">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Trades</p>
          <p className="text-xl font-bold font-mono-data text-slate-200">
            {status?.total_trades ?? 0} <span className="text-xs text-slate-500">({status?.round_trips_today ?? 0}/day)</span>
          </p>
        </div>
      </div>

      {/* Exit Alerts */}
      {exitAlerts.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-red-400 uppercase tracking-wider">Exit Alerts</h2>
          {exitAlerts.map((alert: any) => (
            <div key={alert.ticker} className={cn("glass-card p-4 border-l-4",
              alert.severity === "urgent" ? "border-red-500/50 bg-red-500/5" : "border-amber-500/50 bg-amber-500/5"
            )}>
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-slate-200">{alert.summary}</span>
                </div>
                <Button size="sm" className="bg-red-600 text-white text-xs" onClick={() => handleClose(alert.ticker)}>
                  Close Now
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Active Trades */}
      {activeTrades.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Active Trades</h2>
          {activeTrades.map((trade: any) => (
            <div key={trade.ticker} className="glass-card p-5 border-l-4 border-blue-500/50">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-lg font-semibold text-slate-200">{trade.ticker}</p>
                  <p className="text-xs text-slate-400">{trade.setup}</p>
                </div>
                <div className="flex gap-2">
                  {closing === trade.ticker ? (
                    <div className="flex gap-1">
                      <Input type="number" step="0.01" placeholder="Exit price" value={closePrice}
                        onChange={(e) => setClosePrice(e.target.value)}
                        className="w-24 h-8 text-xs bg-slate-800/50 border-slate-700/50" />
                      <Button size="sm" className="bg-red-600 text-white text-xs h-8" onClick={() => handleClose(trade.ticker)}>Sell</Button>
                      <Button variant="ghost" size="sm" className="text-xs h-8" onClick={() => setClosing(null)}>X</Button>
                    </div>
                  ) : (
                    <Button size="sm" variant="outline" className="border-red-500/50 text-red-400 text-xs"
                      onClick={() => setClosing(trade.ticker)}>Close</Button>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-4 text-xs mt-3 py-2 px-3 rounded-lg bg-slate-800/40 border border-slate-700/30">
                <span className="font-mono-data">Entry: <span className="text-green-400 font-medium">${trade.entry_price}</span></span>
                <span className="font-mono-data">Stop: <span className="text-red-400 font-medium">${trade.stop_price}</span></span>
                <span className="font-mono-data">Target: <span className="text-blue-400 font-medium">${trade.target_price}</span></span>
                <span className="font-mono-data">Shares: <span className="text-slate-300">{trade.shares}</span></span>
                <span className="font-mono-data">Cost: <span className="text-slate-300">${trade.cost}</span></span>
                <span className="font-mono-data text-slate-500">Max hold: {trade.max_hold_date}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Active Dips — stocks currently in the dip */}
      {activeDips.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-amber-400 uppercase tracking-wider">
            Active Dips — In Progress ({activeDips.length})
          </h2>
          {activeDips.map((dip: any) => (
            <div key={dip.ticker} className="glass-card p-5 border-l-4 border-amber-500/50 bg-amber-500/5">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-lg font-semibold text-slate-200">{dip.ticker}</p>
                    <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-red-500/15 text-red-400 border border-red-500/25">
                      DOWN {dip.dip_pct}%
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/15 text-amber-400 border border-amber-500/25">
                      {dip.status}
                    </span>
                  </div>
                  <p className="text-xs text-amber-300/80 mt-1">{dip.alert}</p>
                </div>
                <Button size="sm" className="bg-amber-600 hover:bg-amber-500 text-white text-xs"
                  onClick={() => handleOpen({...dip, quality: 0, setup: `Dip buy: ${dip.status} at $${dip.current_price}`})}>
                  I Bought This
                </Button>
              </div>
              <div className="flex flex-wrap gap-4 text-xs mt-3 py-2 px-3 rounded-lg bg-slate-800/40 border border-slate-700/30">
                <span className="font-mono-data">Now: <span className="text-red-400 font-medium">${dip.current_price}</span></span>
                <span className="font-mono-data">VWAP: <span className="text-blue-400 font-medium">${dip.vwap}</span></span>
                <span className="font-mono-data">Entry zone: <span className="text-green-400 font-medium">${dip.entry_zone}</span></span>
                <span className="font-mono-data">Stop: <span className="text-red-400 font-medium">${dip.stop_price}</span></span>
                <span className="font-mono-data">Target: <span className="text-blue-400 font-medium">${dip.target_price}</span></span>
                <span className="font-mono-data text-slate-500">RSI: {dip.rsi} | Risk: ${dip.risk_dollars}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Confirmed Rebounds */}
      {candidates.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
            Rebound Candidates ({candidates.length})
          </h2>
          {candidates.map((c: any) => (
            <div key={c.ticker} className="glass-card p-5 border-l-4 border-green-500/40">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-lg font-semibold text-slate-200">{c.ticker}</p>
                    <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-green-500/15 text-green-400 border border-green-500/25">
                      Quality: {c.quality}/100
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{c.setup}</p>
                </div>
                <Button size="sm" className="bg-green-600 hover:bg-green-500 text-white text-xs"
                  onClick={() => handleOpen(c)}>
                  I Bought This
                </Button>
              </div>
              <div className="flex flex-wrap gap-4 text-xs mt-3 py-2 px-3 rounded-lg bg-slate-800/40 border border-slate-700/30">
                <span className="font-mono-data">Current: <span className="text-slate-200 font-medium">${c.current_price}</span></span>
                <span className="font-mono-data">Entry: <span className="text-green-400 font-medium">${c.current_price}</span></span>
                <span className="font-mono-data">Stop: <span className="text-red-400 font-medium">${c.stop_price}</span></span>
                <span className="font-mono-data">Target: <span className="text-blue-400 font-medium">${c.target_price}</span></span>
                <span className="font-mono-data text-slate-500">Risk: ${c.risk_dollars} | Reward: ${c.reward_dollars}</span>
              </div>
              <div className="flex flex-wrap gap-3 text-[10px] text-slate-500 mt-2">
                <span>VWAP: ${c.vwap}</span>
                <span>OR Low: ${c.or_low}</span>
                <span>Dip: {c.dip_pct}%</span>
                <span>RSI Low: {c.rsi_low}</span>
                <span>Vol: {c.vol_mult}x</span>
                <span>Shares: {c.suggested_shares}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {candidates.length === 0 && activeTrades.length === 0 && (
        <div className="glass-card p-12 text-center">
          <p className="text-lg text-slate-400 mb-2">No active trades or candidates</p>
          <p className="text-sm text-slate-500">Click "Scan for Setups" during market hours to find rebound opportunities.</p>
          <p className="text-xs text-slate-600 mt-2">Scans after 10:00 AM ET only. Looks for dips + VWAP reclaim with volume.</p>
        </div>
      )}
    </div>
  );
}

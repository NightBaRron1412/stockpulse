"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn, actionBadgeClass } from "@/lib/utils";
import type { ScanStatus, Alert } from "@/lib/types";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/signals", label: "Signals" },
  { href: "/validation", label: "Validation" },
  { href: "/reports", label: "Reports" },
  { href: "/settings", label: "Settings" },
];

export function NavBar() {
  const pathname = usePathname();
  const { data: alerts } = usePolling<Alert[]>(api.alerts, 30000);
  const { data: scanStatus } = usePolling<ScanStatus>(api.scanStatus, 5000);
  const [bellOpen, setBellOpen] = useState(false);
  const [clearedAt, setClearedAt] = useState<string | null>(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("stockpulse_alerts_cleared_at");
    }
    return null;
  });

  const allAlerts = alerts ?? [];
  const visibleAlerts = clearedAt
    ? allAlerts.filter((a) => (a.timestamp ?? "") > clearedAt)
    : allAlerts;
  const unreadCount = visibleAlerts.length;
  const isScanning = scanStatus?.running ?? false;

  return (
    <nav className="sticky top-0 z-50 border-b border-slate-800/50 bg-slate-950/80 backdrop-blur-xl">
      <div className="max-w-[1400px] mx-auto px-6 flex items-center h-14 gap-1">
        <Link href="/" className="flex items-center gap-2 mr-8">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500" />
          <span className="font-semibold text-lg tracking-tight">StockPulse</span>
        </Link>
        {navItems.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "px-3 py-1.5 text-sm rounded-md transition-colors",
                isActive
                  ? "text-slate-100 bg-slate-800/70"
                  : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/50"
              )}
            >
              {item.label}
            </Link>
          );
        })}
        <div className="ml-auto flex items-center gap-4">
          {/* Notification bell with dropdown */}
          <div className="relative">
            <button
              onClick={() => setBellOpen(!bellOpen)}
              className="relative text-slate-400 hover:text-slate-100 transition-colors"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-5 h-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
                />
              </svg>
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-blue-500 text-[10px] font-bold flex items-center justify-center text-white">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </button>

            {/* Dropdown */}
            {bellOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setBellOpen(false)}
                />
                <div className="absolute right-0 top-10 z-50 w-80 max-h-96 overflow-y-auto rounded-xl border border-slate-700/50 bg-slate-900 shadow-2xl shadow-black/60">
                  <div className="px-4 py-3 border-b border-slate-700/50 flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-200">Notifications</span>
                    <button
                      onClick={() => {
                        const now = new Date().toISOString();
                        setBellOpen(false);
                        setClearedAt(now);
                        localStorage.setItem("stockpulse_alerts_cleared_at", now);
                      }}
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      Clear all
                    </button>
                  </div>
                  {visibleAlerts.length === 0 ? (
                    <div className="p-6 text-center text-slate-500 text-sm">
                      No recent alerts
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-700/30">
                      {visibleAlerts.slice(0, 20).map((alert, i) => (
                        <div key={i} className="px-4 py-3 hover:bg-slate-800/30">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium", actionBadgeClass(alert.action ?? "INFO"))}>
                              {alert.action ?? "INFO"}
                            </span>
                            <span className="text-sm font-semibold text-slate-200">
                              {alert.ticker ?? "System"}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 leading-snug line-clamp-2">
                            {alert.thesis ?? ""}
                          </p>
                          <p className="text-[10px] text-slate-600 mt-1 font-mono-data">
                            {alert.timestamp ?? ""}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Scan status indicator */}
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <div
              className={cn(
                "w-2 h-2 rounded-full",
                isScanning ? "bg-blue-500 pulse-scan" : "bg-green-500"
              )}
            />
            <span>
              {isScanning
                ? `Scanning${scanStatus?.progress ? ` ${scanStatus.progress}` : ""}`
                : "Idle"}
            </span>
          </div>
        </div>
      </div>
    </nav>
  );
}

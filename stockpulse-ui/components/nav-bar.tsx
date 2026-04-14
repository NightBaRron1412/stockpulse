"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
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

  const alertCount = alerts?.length ?? 0;
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
          {/* Notification bell */}
          <button className="relative text-slate-400 hover:text-slate-100 transition-colors">
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
            {alertCount > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-blue-500 text-[10px] font-bold flex items-center justify-center text-white">
                {alertCount > 9 ? "9+" : alertCount}
              </span>
            )}
          </button>
          {/* Scan status indicator */}
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <div
              className={cn(
                "w-2 h-2 rounded-full",
                isScanning ? "bg-blue-500 pulse-scan" : "bg-green-500"
              )}
            />
            <span>{isScanning ? "Scanning" : "Idle"}</span>
          </div>
        </div>
      </div>
    </nav>
  );
}

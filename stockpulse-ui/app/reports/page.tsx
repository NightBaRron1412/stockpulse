"use client";

import { useState, useCallback } from "react";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Report } from "@/lib/types";

function reportTypeBadge(type: string): string {
  switch (type) {
    case "morning": return "bg-blue-500/15 text-blue-400 border border-blue-500/25";
    case "eod": return "bg-violet-500/15 text-violet-400 border border-violet-500/25";
    case "intraday": return "bg-orange-500/15 text-orange-400 border border-orange-500/25";
    case "weekly": return "bg-green-500/15 text-green-400 border border-green-500/25";
    default: return "bg-slate-500/15 text-slate-400 border border-slate-500/25";
  }
}

function reportTypeLabel(type: string): string {
  switch (type) {
    case "morning": return "Morning Scan";
    case "eod": return "End of Day";
    case "intraday": return "Intraday Update";
    case "weekly": return "Weekly Digest";
    default: return type;
  }
}

function formatReportTitle(report: Report): string {
  const label = reportTypeLabel(report.type);
  // Extract time from intraday filenames like "2026-04-14-1001-intraday.md"
  if (report.type === "intraday" && report.filename) {
    const match = report.filename.match(/(\d{4})-intraday/);
    if (match) {
      const time = match[1];
      return `${label} (${time.slice(0, 2)}:${time.slice(2)})`;
    }
  }
  return label;
}

export default function ReportsPage() {
  const { data: reports, loading, error } = usePolling<Report[]>(api.reports, 60000);
  const [selectedFilename, setSelectedFilename] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);

  const handleSelect = useCallback(async (filename: string) => {
    setSelectedFilename(filename);
    setContentLoading(true);
    try {
      const result = await api.report(filename);
      setContent(typeof result === "string" ? result : result.content ?? JSON.stringify(result));
    } catch {
      setContent("Failed to load report content.");
    } finally {
      setContentLoading(false);
    }
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Reports</h1>
        <div className="glass-card p-6 animate-pulse">
          <div className="h-64 bg-slate-700/20 rounded" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Reports</h1>
        <div className="glass-card p-6 text-red-400">Failed to load reports: {error}</div>
      </div>
    );
  }

  const reportList = reports ?? [];

  // Group reports by date
  const grouped: Record<string, Report[]> = {};
  for (const r of reportList) {
    const key = r.date || "Unknown";
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(r);
  }
  const sortedDates = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Reports</h1>

      {reportList.length === 0 ? (
        <div className="glass-card p-8 text-center text-slate-500">
          No reports generated yet -- reports appear after market scans
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-10 gap-6" style={{ minHeight: "calc(100vh - 160px)" }}>
          {/* Report list (left 30%) */}
          <div className="lg:col-span-3 glass-card p-0 overflow-hidden">
            <ScrollArea style={{ height: "calc(100vh - 200px)" }}>
              <div className="divide-y divide-slate-700/30">
                {sortedDates.map((date) => (
                  <div key={date}>
                    <div className="px-4 py-2 bg-slate-800/30 text-xs text-slate-500 font-medium sticky top-0 backdrop-blur-sm">
                      {date}
                    </div>
                    {grouped[date].map((r) => (
                      <button
                        key={r.filename}
                        onClick={() => handleSelect(r.filename)}
                        className={cn(
                          "w-full text-left px-4 py-3 hover:bg-slate-800/30 transition-colors",
                          selectedFilename === r.filename && "bg-slate-800/50"
                        )}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium", reportTypeBadge(r.type))}>
                            {r.type}
                          </span>
                        </div>
                        <p className="text-sm text-slate-200 truncate">{formatReportTitle(r)}</p>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>

          {/* Report content (right 70%) */}
          <div className="lg:col-span-7 glass-card p-0 overflow-hidden">
            {!selectedFilename ? (
              <div className="h-full flex items-center justify-center text-slate-500">
                Select a report to view
              </div>
            ) : contentLoading ? (
              <div className="p-6 animate-pulse">
                <div className="h-6 bg-slate-700/50 rounded w-48 mb-4" />
                <div className="space-y-2">
                  <div className="h-4 bg-slate-700/50 rounded w-full" />
                  <div className="h-4 bg-slate-700/50 rounded w-5/6" />
                  <div className="h-4 bg-slate-700/50 rounded w-4/6" />
                </div>
              </div>
            ) : (
              <ScrollArea style={{ height: "calc(100vh - 200px)" }}>
                <div className="p-6 prose-dark">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({ children }) => <h1 className="text-2xl font-bold text-slate-100 mb-4 border-b border-slate-700/50 pb-2">{children}</h1>,
                      h2: ({ children }) => <h2 className="text-xl font-semibold text-slate-200 mt-6 mb-3">{children}</h2>,
                      h3: ({ children }) => <h3 className="text-lg font-semibold text-slate-300 mt-4 mb-2">{children}</h3>,
                      p: ({ children }) => <p className="text-sm text-slate-300 leading-relaxed mb-3">{children}</p>,
                      ul: ({ children }) => <ul className="text-sm text-slate-300 list-disc list-inside mb-3 space-y-1">{children}</ul>,
                      ol: ({ children }) => <ol className="text-sm text-slate-300 list-decimal list-inside mb-3 space-y-1">{children}</ol>,
                      li: ({ children }) => <li className="text-slate-300">{children}</li>,
                      table: ({ children }) => (
                        <div className="overflow-x-auto mb-4">
                          <table className="w-full text-sm border-collapse">{children}</table>
                        </div>
                      ),
                      thead: ({ children }) => <thead className="border-b border-slate-600/50">{children}</thead>,
                      th: ({ children }) => <th className="text-left px-3 py-2 text-xs text-slate-400 font-medium">{children}</th>,
                      td: ({ children }) => <td className="px-3 py-2 text-slate-300 border-b border-slate-700/30 font-mono-data text-xs">{children}</td>,
                      strong: ({ children }) => <strong className="text-slate-100 font-semibold">{children}</strong>,
                      code: ({ children, className }) => {
                        if (className) {
                          return <code className="block bg-slate-800/50 rounded p-3 text-xs font-mono-data text-slate-300 overflow-x-auto mb-3">{children}</code>;
                        }
                        return <code className="bg-slate-800/50 rounded px-1.5 py-0.5 text-xs font-mono-data text-blue-400">{children}</code>;
                      },
                      blockquote: ({ children }) => <blockquote className="border-l-2 border-blue-500/50 pl-4 text-slate-400 italic mb-3">{children}</blockquote>,
                    }}
                  >
                    {content ?? ""}
                  </ReactMarkdown>
                </div>
              </ScrollArea>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

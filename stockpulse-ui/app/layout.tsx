import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import { TooltipProvider } from "@/components/ui/tooltip";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "StockPulse",
  description: "Trading Intelligence Dashboard",
};

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/signals", label: "Signals" },
  { href: "/validation", label: "Validation" },
  { href: "/reports", label: "Reports" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrains.variable}`}>
      <body className="font-sans bg-slate-950 text-slate-100 min-h-screen">
        <TooltipProvider>
          <nav className="sticky top-0 z-50 border-b border-slate-800/50 bg-slate-950/80 backdrop-blur-xl">
            <div className="max-w-[1400px] mx-auto px-6 flex items-center h-14 gap-1">
              <Link href="/" className="flex items-center gap-2 mr-8">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500" />
                <span className="font-semibold text-lg tracking-tight">StockPulse</span>
              </Link>
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-100 rounded-md hover:bg-slate-800/50 transition-colors"
                >
                  {item.label}
                </Link>
              ))}
              <div className="ml-auto flex items-center gap-3">
                <div className="flex items-center gap-1.5 text-xs text-slate-500">
                  <div className="w-2 h-2 rounded-full bg-green-500" />
                  <span>Idle</span>
                </div>
              </div>
            </div>
          </nav>
          <main className="max-w-[1400px] mx-auto px-6 py-6">
            {children}
          </main>
        </TooltipProvider>
      </body>
    </html>
  );
}

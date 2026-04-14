import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { NavBar } from "@/components/nav-bar";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "StockPulse",
  description: "Trading Intelligence Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrains.variable}`}>
      <body className="font-sans bg-slate-950 text-slate-100 min-h-screen">
        <TooltipProvider>
          <NavBar />
          <main className="max-w-[1400px] mx-auto px-6 py-6">
            {children}
          </main>
        </TooltipProvider>
      </body>
    </html>
  );
}

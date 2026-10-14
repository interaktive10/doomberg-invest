import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

// The Logo mark (components/logo.tsx) as the tab icon, inline: no request, so it shows on the sign-in page too.
const ICON =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect x="0.5" y="0.5" width="31" height="31" rx="6.5" fill="#121821" stroke="#2c3947" stroke-width="1"/>' +
      '<rect x="7" y="17" width="4.5" height="8" rx="1.2" fill="#1f8fc8"/><rect x="13.75" y="12" width="4.5" height="13" rx="1.2" fill="#4cc3ff"/>' +
      '<rect x="20.5" y="7" width="4.5" height="18" rx="1.2" fill="#e7edf3"/></svg>',
  );

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
// Figures, dates, tickers and table headers (globals.css --font-mono). Self-hosted by next/font at build time, like Inter.
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-face", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Doomberg Invest", template: "%s · Doomberg Invest" },
  description: "Research tool: evidence first, no orders, no price alerts.",
  robots: { index: false, follow: false },
  icons: { icon: ICON },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#07090c" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}

import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

// The Logo mark (components/logo.tsx) as the tab icon, inline: no request, so it shows on the sign-in page too.
const ICON =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#111827"/>' +
      '<rect x="7" y="17" width="4.5" height="8" rx="1.2" fill="#93c5fd"/><rect x="13.75" y="12" width="4.5" height="13" rx="1.2" fill="#bfdbfe"/>' +
      '<rect x="20.5" y="7" width="4.5" height="18" rx="1.2" fill="#ffffff"/></svg>',
  );

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Doomberg Invest", template: "%s · Doomberg Invest" },
  description: "Research tool: evidence first, no orders, no price alerts.",
  robots: { index: false, follow: false },
  icons: { icon: ICON },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#ffffff" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}

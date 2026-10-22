import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { DARK, LIGHT } from "@/lib/palette";
import { themeMode } from "@/lib/theme-server";
import "./globals.css";

// The Logo mark (components/logo.tsx) as the tab icon, inline: no request, so it shows on the sign-in page too. Its own
// media query follows the device's theme (a favicon can't read the page's CSS variables).
const ICON =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">' +
      `<style>rect{fill:${LIGHT.ink}}path{stroke:${LIGHT["on-ink"]}}` +
      `@media (prefers-color-scheme:dark){rect{fill:${DARK.ink}}path{stroke:${DARK["on-ink"]}}}</style>` +
      '<rect width="32" height="32" rx="10"/>' +
      '<path d="M4 17l5-5 4 3 7-8" transform="translate(7 7) scale(0.75)" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>' +
      "</svg>",
  );

// Inter for everything, self-hosted by next/font at build time (the browser asks no font host).
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Doomberg Invest", template: "%s · Doomberg Invest" },
  description: "Research tool: evidence first, no orders, no price alerts.",
  robots: { index: false, follow: false },
  icons: { icon: ICON },
};

/** The browser's own chrome (the phone's status bar) takes the canvas colour of the theme in use. */
export async function generateViewport(): Promise<Viewport> {
  const mode = await themeMode();
  return {
    width: "device-width",
    initialScale: 1,
    colorScheme: mode === "auto" ? "light dark" : mode,
    themeColor:
      mode === "auto"
        ? [
            { media: "(prefers-color-scheme: light)", color: LIGHT.canvas },
            { media: "(prefers-color-scheme: dark)", color: DARK.canvas },
          ]
        : mode === "light"
          ? LIGHT.canvas
          : DARK.canvas,
  };
}

// Light or Dark from the theme cookie is written on <html> here, on the server, so the first paint is right; Auto
// writes nothing and globals.css follows the device (prefers-color-scheme).
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const mode = await themeMode();
  return (
    <html lang="en" className={inter.variable} data-theme={mode === "auto" ? undefined : mode}>
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}

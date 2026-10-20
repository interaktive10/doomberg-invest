import path from "node:path";
import type { NextConfig } from "next";

// BRIEF §6: server-rendered pages; the service-role key never reaches the browser (lib/supabase/admin.ts is
// server-only). No image optimisation or external hosts are needed, and no file outside web/ ships with a route
// (Settings no longer shows the config files: overhaul PR 4). The trace root stays the repository, as deployed since M7.
// The Screener and the Capex Desk are gone (overhaul PR 4): their old links land on Candidates and on This week.
const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  images: { unoptimized: true },
  outputFileTracingRoot: path.resolve(process.cwd(), ".."),
  async redirects() {
    return [
      { source: "/screener/:path*", destination: "/candidates", permanent: false },
      { source: "/capex/:path*", destination: "/", permanent: false },
    ];
  },
};

export default config;

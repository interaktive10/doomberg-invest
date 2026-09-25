import path from "node:path";
import type { NextConfig } from "next";

// BRIEF §6: server-rendered pages; the service-role key never reaches the browser (lib/supabase/admin.ts is
// server-only). No image optimisation or external hosts are needed. Settings reads ../config/*.yaml (read-only), so
// the trace root is the repository and those files ship with the /settings route.
const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  images: { unoptimized: true },
  outputFileTracingRoot: path.resolve(process.cwd(), ".."),
  outputFileTracingIncludes: { "/settings": ["../config/*.yaml"] },
};

export default config;

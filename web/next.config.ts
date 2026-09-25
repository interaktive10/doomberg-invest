import type { NextConfig } from "next";

// BRIEF §6: server-rendered pages; the service-role key never reaches the browser (lib/supabase/admin.ts is
// server-only). No image optimisation or external hosts are needed.
const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  images: { unoptimized: true },
};

export default config;

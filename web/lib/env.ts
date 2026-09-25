import "server-only";
import { z } from "zod";

// BRIEF §2.4 web env: server-side only. The service-role key is never exposed to the browser (no NEXT_PUBLIC_).
const Env = z.object({
  SUPABASE_URL: z.string().url(),
  SUPABASE_ANON_KEY: z.string().min(1),
  SUPABASE_SERVICE_ROLE_KEY: z.string().min(1),
  APP_ALLOWED_EMAIL: z.string().email(),
});

export type Env = z.infer<typeof Env>;

let cached: Env | undefined;

export function env(): Env {
  cached ??= Env.parse({
    SUPABASE_URL: process.env.SUPABASE_URL,
    SUPABASE_ANON_KEY: process.env.SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY: process.env.SUPABASE_SERVICE_ROLE_KEY,
    APP_ALLOWED_EMAIL: process.env.APP_ALLOWED_EMAIL,
  });
  return cached;
}

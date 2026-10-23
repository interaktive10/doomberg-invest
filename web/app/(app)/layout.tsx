import { Nav } from "@/components/nav";
import { FRAME } from "@/components/page";
import { requireUser } from "@/lib/auth";
import { themeMode } from "@/lib/theme-server";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

// The shell (overhaul PR 6): the header (and the phone's dock), the screen, and the footer with the research-only line,
// once. The stale-data banner is Home's alone (overhaul PR 4). On a phone the footer keeps clear of the floating dock.
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const [{ email }, theme] = await Promise.all([requireUser(), themeMode()]);
  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Nav email={email} theme={theme} />
      <div className="flex-1">{children}</div>
      <footer className={cn(FRAME, "pt-2 pb-[calc(env(safe-area-inset-bottom)_+_6.5rem)] text-center text-[12px] text-subtle md:pb-10")}>
        Research only. No orders, no price alerts.
      </footer>
    </div>
  );
}

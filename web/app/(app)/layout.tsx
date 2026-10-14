import { Nav } from "@/components/nav";
import { StaleBanner } from "@/components/stale";
import { requireUser } from "@/lib/auth";
import { sourceHealth } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const { email } = await requireUser();
  const sources = await sourceHealth();
  return (
    <>
      <Nav email={email} />
      <StaleBanner sources={sources} now={new Date()} />
      {children}
      <footer className="mx-auto max-w-[1440px] border-t border-line px-4 pt-3 pb-8 font-mono text-[11px] text-subtle sm:px-6">
        Research only: no orders, no price alerts. Nothing here is investment advice.
      </footer>
    </>
  );
}

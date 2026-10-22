import { Nav } from "@/components/nav";
import { requireUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

// The stale-data banner is Home's alone (overhaul PR 4); the footer carries the research-only line once.
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const { email } = await requireUser();
  return (
    <>
      <Nav email={email} />
      {children}
      <footer className="mx-auto max-w-[1440px] border-t border-line px-4 pt-3 pb-8 font-mono text-[11px] text-subtle sm:px-6">
        Research only: no orders, no price alerts. Nothing here is investment advice.
      </footer>
    </>
  );
}

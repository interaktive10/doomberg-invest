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
      <footer className="mx-auto max-w-6xl px-4 pt-4 pb-10 text-xs text-gray-700">
        Research only: no orders, no price alerts. Nothing here is investment advice.
      </footer>
    </>
  );
}

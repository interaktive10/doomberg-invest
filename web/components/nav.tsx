import Link from "next/link";
import { Button } from "@/components/ui/button";

const LINKS = [
  ["/", "Home"],
  ["/candidates", "Candidates"],
  ["/theses", "Theses"],
  ["/journal", "Journal"],
  ["/screener", "Screener"],
  ["/capex", "Capex Desk"],
  ["/lab", "Signal Lab"],
  ["/settings", "Settings"],
] as const;

export function Nav({ email }: { email: string }) {
  return (
    <header className="border-b border-gray-300 bg-gray-50">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <Link href="/" className="font-semibold text-gray-900 no-underline">
          Doomberg Invest
        </Link>
        <nav aria-label="Main" className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
          {LINKS.map(([href, label]) => (
            <Link key={href} href={href} className="no-underline hover:underline">
              {label}
            </Link>
          ))}
        </nav>
        <form action="/auth/signout" method="post" className="ml-auto flex items-center gap-2 text-sm">
          <span className="text-gray-700">{email}</span>
          <Button type="submit" variant="outline" size="sm">
            Sign out
          </Button>
        </form>
      </div>
    </header>
  );
}

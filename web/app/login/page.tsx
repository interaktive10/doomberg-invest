import { Logo } from "@/components/logo";
import { SubmitButton } from "@/components/submit-button";
import { Input, Label } from "@/components/ui/input";
import { sendLink } from "./actions";

export const dynamic = "force-dynamic";
export const metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = await searchParams;
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm rounded-md border border-line bg-panel p-6 sm:p-8">
        <Logo className="size-10" />
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-fg">Doomberg Invest</h1>
        <p className="mt-1 text-[13px] text-muted">Sign in with a one-time link sent to the allowed email.</p>
        {q.sent ? (
          <p role="status" className="mt-5 rounded-sm border border-up/40 border-l-2 border-l-up bg-up/10 px-3 py-2 text-[13px] text-fg">
            If that address is allowed, a sign-in link is on its way. Open it on this device.
          </p>
        ) : null}
        {q.error ? (
          <p role="alert" className="mt-5 rounded-sm border border-down/40 border-l-2 border-l-down bg-down/10 px-3 py-2 text-[13px] text-fg">
            {q.error}
          </p>
        ) : null}
        <form action={sendLink} className="mt-6 flex flex-col gap-3">
          <Label htmlFor="email">Email</Label>
          <Input id="email" name="email" type="email" required autoComplete="email" inputMode="email" className="h-10" />
          <SubmitButton size="lg" className="mt-1 w-full">
            Send sign-in link
          </SubmitButton>
        </form>
      </div>
      <p className="mt-6 max-w-sm text-center font-mono text-[11px] text-subtle">
        Research only: no orders, no price alerts. Nothing here is investment advice.
      </p>
    </main>
  );
}

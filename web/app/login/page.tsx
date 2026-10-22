import { Callout } from "@/components/callout";
import { Logo } from "@/components/logo";
import { SubmitButton } from "@/components/submit-button";
import { Field, Input } from "@/components/ui/input";
import { sendLink } from "./actions";

export const dynamic = "force-dynamic";
export const metadata = { title: "Sign in" };

// The sign-in screen, outside the app's shell (overhaul PR 6 look): one sheet with the mark, one line and the email
// field; the answer to a send comes back as a status (the same words whether or not the address is allowed) or an
// alert. The research-only line sits under it, as the shell's footer does on every other screen.
export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = await searchParams;
  return (
    <main id="main" className="flex min-h-dvh flex-col items-center justify-center px-4 py-12">
      <div className="sheet rise flex w-full max-w-sm flex-col gap-6 p-6 sm:p-8">
        <div className="flex flex-col gap-4">
          <span className="flex items-center gap-2.5">
            <Logo className="size-10" />
            <span className="text-[19px] font-bold tracking-[-0.02em] text-fg">doomberg</span>
          </span>
          <div className="flex flex-col gap-1.5">
            <h1 className="text-[28px] leading-tight font-bold tracking-[-0.03em] text-fg">Sign in</h1>
            <p className="text-[15px] text-muted">We email a one-time link to the allowed address. No password.</p>
          </div>
        </div>
        {q.sent ? (
          <Callout tone="good" role="status">
            If that address is allowed, a sign-in link is on its way. Open it on this device.
          </Callout>
        ) : null}
        {q.error ? (
          <Callout tone="bad" role="alert">
            {q.error}
          </Callout>
        ) : null}
        <form action={sendLink} className="flex flex-col gap-4">
          <Field label="Email" htmlFor="email">
            <Input id="email" name="email" type="email" required autoComplete="email" inputMode="email" placeholder="you@example.com" />
          </Field>
          <SubmitButton size="lg" className="w-full">
            Send sign-in link
          </SubmitButton>
        </form>
      </div>
      <p className="mt-6 max-w-sm text-center text-[12px] text-subtle">Research only. No orders, no price alerts.</p>
    </main>
  );
}

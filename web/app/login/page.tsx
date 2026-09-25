import { sendLink } from "./actions";

export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = await searchParams;
  return (
    <main className="mx-auto max-w-sm px-4 py-16">
      <h1 className="text-2xl font-semibold">Doomberg Invest</h1>
      <p className="mt-2 text-gray-700">Sign in with a one-time link sent to the allowed email.</p>
      {q.sent ? (
        <p role="status" className="mt-6 rounded border border-green-700 bg-green-50 p-3">
          If that address is allowed, a sign-in link is on its way. Open it on this device.
        </p>
      ) : null}
      {q.error ? (
        <p role="alert" className="mt-6 rounded border border-red-700 bg-red-50 p-3">
          {q.error}
        </p>
      ) : null}
      <form action={sendLink} className="mt-6 flex flex-col gap-3">
        <label htmlFor="email" className="font-medium">
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          required
          autoComplete="email"
          className="rounded border border-gray-500 px-3 py-2"
        />
        <button type="submit" className="rounded bg-blue-800 px-4 py-2 font-medium text-white hover:bg-blue-900">
          Send sign-in link
        </button>
      </form>
    </main>
  );
}

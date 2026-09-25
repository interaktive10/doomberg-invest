import type { APIRequestContext } from "@playwright/test";

// The local Supabase stack's mail catcher: Mailpit (current CLI) or Inbucket (older CLI), on port 54324.
const MAIL = process.env.MAIL_URL ?? "http://127.0.0.1:54324";

interface Found {
  id: string;
  html: string;
}

async function mailpit(request: APIRequestContext, email: string): Promise<Found[] | null> {
  const r = await request.get(`${MAIL}/api/v1/messages?limit=50`);
  if (!r.ok()) return null;
  const body = (await r.json()) as { messages?: { ID: string; To?: { Address: string }[] }[] };
  if (!Array.isArray(body.messages)) return null;
  const mine = body.messages.filter((m) => (m.To ?? []).some((t) => t.Address.toLowerCase() === email.toLowerCase()));
  return Promise.all(
    mine.map(async (m) => {
      const msg = (await (await request.get(`${MAIL}/api/v1/message/${m.ID}`)).json()) as { HTML?: string; Text?: string };
      return { id: m.ID, html: `${msg.HTML ?? ""}\n${msg.Text ?? ""}` };
    }),
  );
}

async function inbucket(request: APIRequestContext, email: string): Promise<Found[]> {
  const box = email.split("@")[0] ?? email;
  const r = await request.get(`${MAIL}/api/v1/mailbox/${box}`);
  if (!r.ok()) return [];
  const list = (await r.json()) as { id: string }[];
  return Promise.all(
    list.map(async (m) => {
      const msg = (await (await request.get(`${MAIL}/api/v1/mailbox/${box}/${m.id}`)).json()) as { body?: { html?: string; text?: string } };
      return { id: m.id, html: `${msg.body?.html ?? ""}\n${msg.body?.text ?? ""}` };
    }),
  );
}

export async function messages(request: APIRequestContext, email: string): Promise<Found[]> {
  return (await mailpit(request, email)) ?? inbucket(request, email);
}

export async function clearMail(request: APIRequestContext): Promise<void> {
  await request.delete(`${MAIL}/api/v1/messages`).catch(() => undefined);
}

/** The sign-in link of the newest email to `email` (polls until one arrives). */
export async function signInLink(request: APIRequestContext, email: string, timeoutMs = 30_000): Promise<string> {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    for (const m of (await messages(request, email)).reverse()) {
      const link = /href="([^"]*\/verify\?[^"]*)"/.exec(m.html)?.[1] ?? /(https?:\/\/\S*\/verify\?\S*)/.exec(m.html)?.[1];
      if (link) return link.replace(/&amp;/g, "&");
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no sign-in email for ${email} within ${timeoutMs} ms`);
}

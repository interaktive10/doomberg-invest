// Small helpers for server actions (pure, so tests/forms.test.ts covers them).

export function field(form: FormData, name: string): string {
  const v = form.get(name);
  return typeof v === "string" ? v.trim() : "";
}

/** A same-site path to return to after an action; anything else (an absolute or protocol-relative URL) falls back,
 * so a form field can't turn an action into an open redirect. */
export function safePath(path: string, fallback: string): string {
  return path.startsWith("/") && !path.startsWith("//") && !path.includes("\\") ? path : fallback;
}

/** path with ?error= or ?ok= set (and the other removed), keeping its other query parameters. */
export function withMessage(path: string, key: "error" | "ok", message: string): string {
  const i = path.indexOf("?");
  const base = i < 0 ? path : path.slice(0, i);
  const q = new URLSearchParams(i < 0 ? "" : path.slice(i + 1));
  q.delete("error");
  q.delete("ok");
  q.set(key, message);
  return `${base}?${q.toString()}`;
}

export const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type Query = Record<string, string | string[] | undefined>;

/** The first value of a query parameter. */
export function one(q: Query, key: string): string | undefined {
  const v = q[key];
  return Array.isArray(v) ? v[0] : v;
}

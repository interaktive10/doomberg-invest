import "server-only";
import { cookies } from "next/headers";
import { parseTheme, THEME_COOKIE, type ThemeMode } from "@/lib/theme";

/** The theme this browser chose (its cookie; none is Auto), read on the server so the first paint is right. */
export async function themeMode(): Promise<ThemeMode> {
  const jar = await cookies();
  return parseTheme(jar.getAll().find((c) => c.name === THEME_COOKIE)?.value);
}

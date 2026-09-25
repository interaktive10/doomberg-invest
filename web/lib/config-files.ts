import "server-only";
import { readFile } from "node:fs/promises";
import path from "node:path";

// Settings shows the repo's config files read-only (BRIEF §6: quotas; weights change only through a PR). The web app
// runs from web/, so the files are one level up; next.config.ts traces them into the deployment.
export const CONFIG_FILES = ["quotas.yaml", "weights.yaml", "universe_us.yaml", "universe_in.yaml", "staleness.yaml"] as const;

export async function configText(name: (typeof CONFIG_FILES)[number]): Promise<string | null> {
  try {
    return await readFile(path.join(process.cwd(), "..", "config", name), "utf8");
  } catch {
    return null;
  }
}

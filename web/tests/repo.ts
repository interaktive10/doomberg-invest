import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** A file of the repository (web/ is one level down), for tests that pin the web app to the pipeline's files. */
export function repoFile(path: string): string {
  return readFileSync(fileURLToPath(new URL(`../../${path}`, import.meta.url)), "utf8");
}

/** The `key: value` lines of a top-level YAML mapping (enough for config/staleness.yaml's flat blocks). */
export function yamlBlock(text: string, block: string): Record<string, string> {
  const out: Record<string, string> = {};
  let inside = false;
  for (const line of text.split("\n")) {
    if (/^\S/.test(line)) inside = line.startsWith(`${block}:`);
    else if (inside) {
      const m = /^\s+([\w-]+):\s*([^#\s]+)/.exec(line);
      if (m?.[1] && m[2]) out[m[1]] = m[2];
    }
  }
  return out;
}

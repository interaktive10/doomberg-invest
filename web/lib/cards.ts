import { CONTEXT_NAME, humanize, RED_FLAG_NAME, SIGNAL_NAME } from "@/lib/labels";

// Display helpers for the markdown the pipeline writes (thesis cards, the digest). Display only: the stored text is
// what pipeline/thesis/validate.py checked, and nothing here changes it.

/** pipeline/thesis/validate.py CITE: an inline pack id, [m:...], [f:...], [s:...] or [c:...]. */
export const CITE = /\[((?:m|f|s|c):[^\]\s]+)\]/g;

/** The markdown without the section titled `title` (its heading down to the next heading of the same or a higher
 * level), for a section the page shows live next to the text (a card's kill criteria, the digest's source health). */
export function stripSection(md: string, title: string): string {
  const out: string[] = [];
  let skipping = 0; // the level of the heading being skipped; 0 = keeping
  for (const line of md.split("\n")) {
    const h = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (h) {
      const level = h[1]!.length;
      if (skipping && level <= skipping) skipping = 0;
      if (!skipping && h[2]!.trim().toLowerCase() === title.toLowerCase()) {
        skipping = level;
        continue;
      }
    }
    if (!skipping) out.push(line);
  }
  return out.join("\n");
}

/** The markdown without its leading "# title" line (the page's own header already says it). */
export function stripTitle(md: string): string {
  const lines = md.split("\n");
  const first = lines.findIndex((l) => l.trim() !== "");
  if (first === -1 || !/^#\s/.test(lines[first]!)) return md;
  return lines.slice(first + 1).join("\n").replace(/^\s*\n/, "");
}

/** The fact ids a text cites, in order of first appearance (fact 1, fact 2, ...). */
export function factOrder(md: string): string[] {
  const out: string[] = [];
  for (const m of md.matchAll(CITE)) {
    const id = m[1]!;
    if (id.startsWith("f:") && !out.includes(id)) out.push(id);
  }
  return out;
}

export interface CiteView {
  label: string;
  title: string;
  href: string | null;
}

/** How a citation shows in a card: a short label, the full id as its title, and where its evidence is on the company
 * page (facts carry anchors there: #fact-<id>). */
export function citeView(id: string, companyId: string | null, facts: readonly string[]): CiteView {
  const page = companyId ? `/company/${companyId}` : null;
  const at = (hash: string) => (page ? `${page}#${hash}` : null);
  const [kind, ...rest] = id.split(":");
  const body = rest.join(":");
  switch (kind) {
    case "f": {
      const n = facts.indexOf(id) + 1;
      return { label: n > 0 ? `fact ${n}` : "fact", title: `Verified fact ${body}`, href: at(`fact-${body}`) };
    }
    case "m": {
      const dated = /^(.*):(\d{4}-\d{2}-\d{2})$/.exec(body); // m:<metric>:<period end> (validate.py METRIC_ID)
      const name = humanize(dated ? dated[1] : body);
      return { label: dated ? `${name} ${dated[2]}` : name, title: `Metric ${body}`, href: at("fundamentals") };
    }
    case "s":
      // the Company page has no signal timeline any more (overhaul PR 4): its score line is at the top
      return { label: body, title: SIGNAL_NAME[body] ?? RED_FLAG_NAME[body] ?? `Signal ${body}`, href: page };
    case "c":
      return { label: body, title: CONTEXT_NAME[body] ?? `Context ${body}`, href: at("context") };
    default:
      return { label: id, title: id, href: null };
  }
}

// A minimal hast shape (the rehype tree react-markdown builds); @types/hast isn't a direct dependency.
interface HastNode {
  type: string;
  value?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

function splitCites(node: HastNode): void {
  if (!node.children) return;
  const out: HastNode[] = [];
  for (const child of node.children) {
    if (child.type === "text" && child.value !== undefined && child.value.includes("[")) {
      let last = 0;
      for (const m of child.value.matchAll(CITE)) {
        const at = m.index ?? 0;
        if (at > last) out.push({ type: "text", value: child.value.slice(last, at) });
        out.push({ type: "element", tagName: "span", properties: { dataCite: m[1] }, children: [{ type: "text", value: m[0] }] });
        last = at + m[0].length;
      }
      if (last < child.value.length) out.push({ type: "text", value: child.value.slice(last) });
      continue;
    }
    if (!(child.type === "element" && (child.tagName === "code" || child.tagName === "pre"))) splitCites(child);
    out.push(child);
  }
  node.children = out;
}

/** A rehype plugin: each inline citation becomes <span data-cite="<id>">, which components/markdown.tsx renders as a
 * chip. Code spans are left alone. */
export function rehypeCites() {
  return (tree: HastNode) => splitCites(tree);
}

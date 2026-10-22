import Link from "next/link";
import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { rehypeCites, type CiteView } from "@/lib/cards";
import { shiftedHeading } from "@/lib/headings";

type HeadingProps = ComponentProps<"h1"> & { node?: unknown };

function heading(level: 1 | 2 | 3 | 4 | 5 | 6) {
  const Tag = shiftedHeading(level);
  return function Heading({ node: _node, ...props }: HeadingProps) {
    return <Tag {...props} />;
  };
}

// A citation as a small soft pill after the sentence it backs: accent on its own tint when it opens the fact or figure
// on this site, grey when it has nowhere to go. Both colours hold 4.5:1 on their tint in both themes
// (tests/palette.test.ts).
const CHIP = "num ml-1 inline-block rounded-full px-1.5 align-baseline text-[0.75em] leading-[1.6] font-semibold whitespace-nowrap";

function Cite({ view }: { view: CiteView }) {
  return view.href ? (
    <Link href={view.href} title={view.title} className={`${CHIP} bg-accent/10 text-accent no-underline transition-colors duration-150 hover:bg-accent/15 hover:text-accent-hover`}>
      {view.label}
    </Link>
  ) : (
    <span title={view.title} className={`${CHIP} bg-hover text-muted`}>
      {view.label}
    </span>
  );
}

/** The digest and thesis cards are markdown the pipeline wrote; raw HTML in it is not rendered. Prose styles are
 * app/globals.css .prose-md (theme colours only, so both themes read). Its headings sit under the Section's h2
 * (h1 -> h3). Tables scroll sideways in a focusable box on a phone (axe scrollable-region-focusable). With `cite`,
 * inline citations ([f:...], [m:...], [s:...], [c:...]) show as chips. */
export function Markdown({ text, cite }: { text: string; cite?: (id: string) => CiteView }) {
  return (
    <div className="prose-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={cite ? [rehypeCites as never] : []}
        skipHtml
        components={{
          h1: heading(1),
          h2: heading(2),
          h3: heading(3),
          h4: heading(4),
          h5: heading(5),
          h6: heading(6),
          table: ({ node: _node, ...props }: ComponentProps<"table"> & { node?: unknown }) => (
            <div className="relative overflow-x-auto rounded-tile" tabIndex={0}>
              <table {...props} />
            </div>
          ),
          span: ({ node: _node, ...props }: ComponentProps<"span"> & { node?: unknown; "data-cite"?: string }) => {
            const id = props["data-cite"];
            return typeof id === "string" && cite ? <Cite view={cite(id)} /> : <span {...props} />;
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

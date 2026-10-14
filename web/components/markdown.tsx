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

function Cite({ view }: { view: CiteView }) {
  const chip = "ml-1 inline-block rounded-sm bg-raised px-1 py-px align-baseline font-mono text-[0.75em] leading-snug font-medium whitespace-nowrap";
  return view.href ? (
    <Link href={view.href} title={view.title} className={`${chip} text-accent no-underline ring-1 ring-line-strong ring-inset hover:bg-hover hover:underline`}>
      {view.label}
    </Link>
  ) : (
    <span title={view.title} className={`${chip} text-muted`}>
      {view.label}
    </span>
  );
}

/** The digest, the Capex brief and thesis cards are markdown the pipeline wrote; raw HTML in it is not rendered.
 * Its headings sit under the Section's h2 (h1 -> h3). Tables scroll sideways in a focusable box on a phone (axe
 * scrollable-region-focusable). With `cite`, inline citations ([f:...], [m:...], [s:...], [c:...]) show as chips. */
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
            <div className="relative overflow-x-auto" tabIndex={0}>
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

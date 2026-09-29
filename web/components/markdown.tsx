import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { shiftedHeading } from "@/lib/headings";

type HeadingProps = ComponentProps<"h1"> & { node?: unknown };

function heading(level: 1 | 2 | 3 | 4 | 5 | 6) {
  const Tag = shiftedHeading(level);
  return function Heading({ node: _node, ...props }: HeadingProps) {
    return <Tag {...props} />;
  };
}

/** The digest, the Capex brief and thesis cards are markdown the pipeline wrote; raw HTML in it is not rendered.
 * Its headings sit under the Section's h2 (h1 -> h3). Tables scroll sideways in a focusable box on a phone (axe
 * scrollable-region-focusable). */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          h1: heading(1),
          h2: heading(2),
          h3: heading(3),
          h4: heading(4),
          h5: heading(5),
          h6: heading(6),
          table: ({ node: _node, ...props }: ComponentProps<"table"> & { node?: unknown }) => (
            <div className="overflow-x-auto" tabIndex={0}>
              <table {...props} />
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

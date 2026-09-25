import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** The digest, the Capex brief and thesis cards are markdown the pipeline wrote; raw HTML in it is not rendered.
 * Tables scroll sideways in a focusable box on a phone (axe scrollable-region-focusable). */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          table: ({ node: _node, ...props }) => (
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

import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Table as clean rows: small grey column labels, a hairline between rows, no grid, and a soft fill under the
// row the pointer is on. Use it only where many rows really need columns; a short list reads better as tiles.
// The wrapper scrolls sideways on a phone (390 px) instead of the page (it is `relative`, so screen-reader-only text in
// a cell is clipped with the table instead of widening the page); it is focusable so a keyboard can scroll it too (axe
// scrollable-region-focusable), and a named region when `label` is given. `num` right-aligns a numeric column in
// tabular figures; `sticky` keeps a column (the company) in view while the rest scrolls.
export function Table({ className, label, ...props }: ComponentProps<"table"> & { label?: string }) {
  return (
    <div className="relative w-full overflow-x-auto rounded-tile" tabIndex={0} {...(label ? { role: "region", "aria-label": label } : {})}>
      <table className={cn("w-full caption-bottom border-collapse text-[14px]", className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: ComponentProps<"thead">) {
  return <thead className={cn("[&_tr]:border-t-0", className)} {...props} />;
}

export function TableBody(props: ComponentProps<"tbody">) {
  return <tbody {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr className={cn("group border-t border-line", className)} {...props} />;
}

const STICKY = "sticky left-0 z-10 bg-panel shadow-[1px_0_0_var(--line)]";

export function TableHead({ className, num, sticky, ...props }: ComponentProps<"th"> & { num?: boolean; sticky?: boolean }) {
  return (
    <th
      scope="col"
      className={cn("caps h-9 px-3 text-left align-middle whitespace-nowrap", num && "text-right", sticky && STICKY, className)}
      {...props}
    />
  );
}

export function TableCell({ className, num, sticky, ...props }: ComponentProps<"td"> & { num?: boolean; sticky?: boolean }) {
  return (
    <td
      className={cn(
        "px-3 py-2.5 align-top text-fg transition-colors duration-150 group-hover:bg-raised",
        num && "num text-right whitespace-nowrap",
        sticky && STICKY,
        sticky && "group-hover:bg-raised",
        className,
      )}
      {...props}
    />
  );
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("mt-2 text-left text-[13px] text-subtle", className)} {...props} />;
}

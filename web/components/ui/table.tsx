import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Table. The wrapper scrolls sideways on a phone (390 px) instead of the page (it is `relative`, so screen-
// reader-only text in a cell is clipped with the table instead of widening the page); it is focusable so a
// keyboard can scroll it too (axe scrollable-region-focusable), and a named region when `label` is given.
// `num` right-aligns a numeric column in monospace tabular figures; `sticky` keeps a column (the company) in view
// while the rest scrolls.
export function Table({ className, label, ...props }: ComponentProps<"table"> & { label?: string }) {
  return (
    <div className="relative w-full overflow-x-auto" tabIndex={0} {...(label ? { role: "region", "aria-label": label } : {})}>
      <table className={cn("w-full caption-bottom border-collapse text-[13px]", className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: ComponentProps<"thead">) {
  return <thead className={cn("border-b border-line-strong", className)} {...props} />;
}

export function TableBody(props: ComponentProps<"tbody">) {
  return <tbody {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr className={cn("group border-b border-line last:border-0", className)} {...props} />;
}

const STICKY = "sticky left-0 z-10 bg-panel shadow-[inset_-1px_0_0_var(--color-line-strong)]";

export function TableHead({ className, num, sticky, ...props }: ComponentProps<"th"> & { num?: boolean; sticky?: boolean }) {
  return (
    <th
      scope="col"
      className={cn("caps h-8 px-3 text-left align-middle whitespace-nowrap", num && "text-right", sticky && STICKY, className)}
      {...props}
    />
  );
}

export function TableCell({ className, num, sticky, ...props }: ComponentProps<"td"> & { num?: boolean; sticky?: boolean }) {
  return (
    <td
      className={cn(
        "px-3 py-2 align-top text-fg group-hover:bg-hover",
        num && "num text-right whitespace-nowrap",
        sticky && STICKY,
        sticky && "group-hover:bg-hover",
        className,
      )}
      {...props}
    />
  );
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("mt-2 text-left text-xs text-subtle", className)} {...props} />;
}

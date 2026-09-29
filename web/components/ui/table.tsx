import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// shadcn/ui Table. The wrapper scrolls sideways on a phone (390 px) instead of the page (it is `relative`, so screen-
// reader-only text in a cell is clipped with the table instead of widening the page); it is focusable so a
// keyboard can scroll it too (axe scrollable-region-focusable), and a named region when `label` is given.
// `num` right-aligns a numeric column in tabular figures; `sticky` keeps a column (the company) in view while the
// rest scrolls.
export function Table({ className, label, ...props }: ComponentProps<"table"> & { label?: string }) {
  return (
    <div className="relative w-full overflow-x-auto" tabIndex={0} {...(label ? { role: "region", "aria-label": label } : {})}>
      <table className={cn("w-full caption-bottom border-collapse text-sm", className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: ComponentProps<"thead">) {
  return <thead className={cn("border-b border-gray-200", className)} {...props} />;
}

export function TableBody(props: ComponentProps<"tbody">) {
  return <tbody {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr className={cn("group border-b border-gray-100 last:border-0", className)} {...props} />;
}

const STICKY = "sticky left-0 z-10 bg-white shadow-[inset_-1px_0_0_var(--color-gray-200)]";

export function TableHead({ className, num, sticky, ...props }: ComponentProps<"th"> & { num?: boolean; sticky?: boolean }) {
  return (
    <th
      scope="col"
      className={cn(
        "px-3 py-2 text-left text-xs font-semibold tracking-wide whitespace-nowrap text-gray-700 uppercase",
        num && "text-right",
        sticky && STICKY,
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({ className, num, sticky, ...props }: ComponentProps<"td"> & { num?: boolean; sticky?: boolean }) {
  return (
    <td
      className={cn(
        "px-3 py-2.5 align-top text-gray-900 group-hover:bg-gray-50",
        num && "text-right whitespace-nowrap tabular-nums",
        sticky && STICKY,
        sticky && "group-hover:bg-gray-50",
        className,
      )}
      {...props}
    />
  );
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("mt-2 text-left text-xs text-gray-700", className)} {...props} />;
}

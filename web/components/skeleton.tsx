import { FRAME } from "@/components/page";
import { cn } from "@/lib/utils";

// A screen's first paint while its server reads run (the 2026-11 redesign, docs/SPEC_ISSUES.md 65): a tapped link
// shows this at once, instead of the old page sitting still for seconds. Shapes only, no words to read. Only on screens
// with no server action that redirects back to them (components/link-pending.tsx says why).
export function ScreenSkeleton() {
  return (
    <main id="main" aria-busy="true" className={cn(FRAME, "flex flex-col gap-6 pt-3 pb-8 md:pt-4")}>
      <span className="sr-only" role="status">
        Loading
      </span>
      <div className="flex flex-col gap-3">
        <span className="skeleton h-10 w-56 md:h-12" />
        <span className="skeleton h-5 w-80 max-w-full" />
      </div>
      <div className="sheet flex flex-col gap-4 p-5 md:p-6">
        <span className="skeleton h-6 w-40" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className="skeleton h-20" style={{ animationDelay: `${i * 80}ms` }} />
          ))}
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        {[0, 1].map((s) => (
          <div key={s} className="sheet flex flex-col gap-3 p-5 md:p-6">
            <span className="skeleton h-6 w-32" />
            {[0, 1, 2, 3].map((i) => (
              <span key={i} className="skeleton h-14" style={{ animationDelay: `${(s * 4 + i) * 60}ms` }} />
            ))}
          </div>
        ))}
      </div>
    </main>
  );
}

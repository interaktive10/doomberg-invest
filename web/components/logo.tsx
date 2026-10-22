/** The app's mark: a rising line on an ink tile (white on near-black in light, near-black on ivory in dark), from the
 * theme's ink and on-ink colours. Decorative; the name sits next to it. app/layout.tsx ICON repeats it as the tab icon:
 * change both together. */
export function Logo({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={className}>
      <rect width="32" height="32" rx="10" className="fill-ink" />
      <path
        d="M4 17l5-5 4 3 7-8"
        transform="translate(7 7) scale(0.75)"
        fill="none"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-on-ink"
      />
    </svg>
  );
}

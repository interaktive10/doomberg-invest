/** The app's mark: three rising bars (evidence building up), in the theme's raised tile, accent and fg (app/globals.css).
 * Decorative; the name sits next to it. app/layout.tsx ICON repeats it as the tab icon: change both together. */
export function Logo({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={className}>
      <rect x="0.5" y="0.5" width="31" height="31" rx="6.5" fill="#121821" stroke="#2c3947" strokeWidth="1" />
      <rect x="7" y="17" width="4.5" height="8" rx="1.2" fill="#1f8fc8" />
      <rect x="13.75" y="12" width="4.5" height="13" rx="1.2" fill="#4cc3ff" />
      <rect x="20.5" y="7" width="4.5" height="18" rx="1.2" fill="#e7edf3" />
    </svg>
  );
}

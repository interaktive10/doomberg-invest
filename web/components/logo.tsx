/** The app's mark: three rising bars (evidence building up). Decorative; the name sits next to it. */
export function Logo({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={className}>
      <rect width="32" height="32" rx="7" fill="#111827" />
      <rect x="7" y="17" width="4.5" height="8" rx="1.2" fill="#93c5fd" />
      <rect x="13.75" y="12" width="4.5" height="13" rx="1.2" fill="#bfdbfe" />
      <rect x="20.5" y="7" width="4.5" height="18" rx="1.2" fill="#ffffff" />
    </svg>
  );
}

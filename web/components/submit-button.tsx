"use client";

import type { ComponentProps } from "react";
import { useFormStatus } from "react-dom";
import { Button } from "@/components/ui/button";

/** A form's submit button that shows the form is working (and can't be sent twice) until the server action answers.
 * Its name stays the same while it works. */
export function SubmitButton({ children, disabled, ...props }: Omit<ComponentProps<typeof Button>, "type">) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending || disabled} aria-busy={pending || undefined} {...props}>
      {pending ? (
        <svg viewBox="0 0 24 24" aria-hidden="true" className="size-3.5 animate-spin">
          <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="3" strokeOpacity="0.3" />
          <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        </svg>
      ) : null}
      {children}
    </Button>
  );
}

import * as React from "react";

import { cn } from "@/lib/utils";

/** The shared input shape. Never below 16px, or iOS zooms on focus. */
export const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]",
        "px-4 py-3 text-[var(--color-fg)] placeholder:text-[var(--color-muted)]",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-[var(--color-accent)]/45",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.ComponentProps<"textarea">
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full resize-y rounded-xl border border-[var(--color-border)]",
      "bg-[var(--color-surface)] px-4 py-3 text-[var(--color-fg)]",
      "placeholder:text-[var(--color-muted)] focus-visible:outline-none",
      "focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/45",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

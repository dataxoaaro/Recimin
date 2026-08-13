import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Sizes follow Arboretium's touch-target rule rather than shadcn's defaults:
 * 40 / 48 / 56px, because this app is used with greasy hands at arm's length.
 * `destructive` is text-only on purpose — destructive actions recede.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-2xl font-medium select-none " +
    "transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 " +
    "focus-visible:ring-[var(--color-accent)]/45 disabled:opacity-50 " +
    "disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-strong)] " +
          "active:bg-[var(--color-accent-strong)]",
        secondary:
          "bg-[var(--color-surface)] text-[var(--color-fg)] border " +
          "border-[var(--color-border)] hover:bg-black/[0.03] dark:hover:bg-white/[0.04]",
        ghost:
          "bg-transparent text-[var(--color-fg)] hover:bg-black/5 dark:hover:bg-white/[0.06]",
        destructive:
          "bg-transparent text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10",
      },
      size: {
        sm: "min-h-10 px-4 text-sm gap-1.5",
        md: "min-h-12 px-5 text-base gap-2",
        lg: "min-h-14 px-6 text-lg gap-2.5",
        icon: "min-h-12 min-w-12 rounded-full",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };

import * as React from "react";

import { cn } from "@/lib/utils";

/** Surface + hairline + rounded-2xl. The canonical container. */
export function Card({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]",
        className,
      )}
      {...props}
    />
  );
}

/** The dashed variant used for every empty state. */
export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-[var(--color-border)] p-6 text-[var(--color-muted)]">
      <p className="mb-1 font-medium text-[var(--color-fg)]">{title}</p>
      <p>{body}</p>
    </div>
  );
}

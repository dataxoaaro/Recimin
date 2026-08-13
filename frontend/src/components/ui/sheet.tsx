import { X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The responsive sheet, inherited verbatim from Arboretium's CellSheet:
 * full-width bottom sheet on phones, 440px right drawer from `sm:` up.
 * Sticky header, scrolling body, optional sticky footer. Closes on backdrop
 * tap and Escape.
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "fixed inset-x-0 bottom-0 z-50 flex max-h-[85vh] flex-col rounded-t-3xl border-t",
          "sm:inset-x-auto sm:top-0 sm:right-0 sm:bottom-0 sm:max-h-none sm:w-[440px]",
          "sm:rounded-none sm:border-t-0 sm:border-l",
          "border-[var(--color-border)] bg-[var(--color-bg)] shadow-2xl",
        )}
      >
        <header className="flex shrink-0 items-center justify-between border-b border-[var(--color-border)] px-5 py-4">
          <h2 className="font-[family-name:var(--font-display)] text-xl font-semibold">
            {title}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="-mr-2 inline-flex min-h-12 min-w-12 items-center justify-center rounded-full text-[var(--color-muted)] transition-colors hover:bg-black/5 dark:hover:bg-white/[0.06]"
          >
            <X size={22} aria-hidden />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-4 pb-safe">
          {children}
        </div>

        {footer && (
          <footer className="flex shrink-0 items-center gap-3 border-t border-[var(--color-border)] p-4 pb-safe">
            {footer}
          </footer>
        )}
      </div>
    </>
  );
}

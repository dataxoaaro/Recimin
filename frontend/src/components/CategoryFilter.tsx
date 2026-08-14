import { useCategories } from "@/hooks/useCategories";
import { t } from "@/lib/strings";
import { cn } from "@/lib/utils";

/**
 * Horizontally scrollable filter chips, 36px tall.
 *
 * Not 44: that is Apple's guidance for a primary action, and applied to a row
 * of a dozen secondary filters it made the row read as the heaviest element on
 * the library screen. 36px clears WCAG 2.5.8's 24px target minimum comfortably
 * and matches what iOS itself uses for chip rows.
 */
export function CategoryFilter({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (next: string | null) => void;
}) {
  const categories = useCategories();

  const chip = (active: boolean) =>
    cn(
      "inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm",
      "transition-colors",
      active
        ? "border-[var(--color-accent)] bg-black/[0.05] font-medium dark:bg-white/[0.06]"
        : "border-[var(--color-border)] hover:bg-black/[0.03] dark:hover:bg-white/[0.04]",
    );

  return (
    <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
      <button className={chip(value === null)} onClick={() => onChange(null)}>
        {t.allCategories}
      </button>
      {categories.map((category) => (
        <button
          key={category.key}
          className={chip(value === category.key)}
          onClick={() => onChange(category.key)}
        >
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ background: category.colour }}
          />
          {category.label}
        </button>
      ))}
    </div>
  );
}

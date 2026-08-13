import { Clock, Heart } from "lucide-react";
import { Link } from "react-router-dom";

import { categoryColour, categoryLabel, useCategories } from "@/hooks/useCategories";
import { t } from "@/lib/strings";
import type { RecipeSummary } from "@/lib/types";

/** A library grid tile. The whole card is one tap target. */
export function RecipeCard({ recipe }: { recipe: RecipeSummary }) {
  const categories = useCategories();

  return (
    <Link
      to={`/recipes/${recipe.id}`}
      className="group block overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] transition-colors hover:bg-black/[0.03] dark:hover:bg-white/[0.04]"
    >
      <div className="relative aspect-[4/3] bg-[var(--color-bg)]">
        {recipe.hero_media_id ? (
          <img
            src={`/api/media/${recipe.hero_media_id}`}
            alt={recipe.title}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-[var(--color-border)]">
            <span
              className="h-6 w-6 rounded-full"
              style={{ background: categoryColour(categories, recipe.category) }}
            />
          </div>
        )}
        {recipe.is_favourite && (
          <Heart
            size={18}
            aria-hidden
            className="absolute top-2 right-2 fill-[var(--color-accent)] text-[var(--color-accent)] drop-shadow"
          />
        )}
        {recipe.status === "draft" && (
          <span className="absolute top-2 left-2 rounded-full bg-[var(--color-amber)] px-2 py-0.5 text-xs font-medium text-[var(--color-fg)]">
            {t.draft}
          </span>
        )}
      </div>

      <div className="p-3">
        <p className="line-clamp-2 font-[family-name:var(--font-display)] text-base font-medium">
          {recipe.title}
        </p>
        <div className="mt-1 flex items-center gap-1.5 text-sm text-[var(--color-muted)]">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ background: categoryColour(categories, recipe.category) }}
          />
          <span className="truncate">{categoryLabel(categories, recipe.category)}</span>
          {recipe.total_time_minutes != null && (
            <>
              <Clock size={14} aria-hidden className="ml-auto shrink-0" />
              <span className="shrink-0">{t.minutes(recipe.total_time_minutes)}</span>
            </>
          )}
        </div>
      </div>
    </Link>
  );
}

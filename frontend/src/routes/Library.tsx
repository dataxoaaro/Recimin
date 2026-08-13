import * as React from "react";

import { EmptyState } from "@/components/ui/card";
import { api } from "@/lib/api";
import { t } from "@/lib/strings";
import type { RecipeSummary } from "@/lib/types";

/** The library grid. Recipe cards and filters arrive in Phase 4. */
export function Library() {
  const [recipes, setRecipes] = React.useState<RecipeSummary[] | null>(null);
  const [error, setError] = React.useState(false);

  React.useEffect(() => {
    api.listRecipes().then(setRecipes).catch(() => setError(true));
  }, []);

  if (error) return <p className="text-[var(--color-danger)]">{t.loadFailed}</p>;
  if (recipes === null) return <p className="text-[var(--color-muted)]">{t.loading}</p>;
  if (recipes.length === 0) {
    return <EmptyState title={t.libraryEmptyTitle} body={t.libraryEmptyBody} />;
  }

  return (
    <ul className="space-y-2">
      {recipes.map((recipe) => (
        <li
          key={recipe.id}
          className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
        >
          <p className="font-[family-name:var(--font-display)] text-base font-medium">
            {recipe.title}
          </p>
          <p className="text-sm text-[var(--color-muted)]">{recipe.category}</p>
        </li>
      ))}
    </ul>
  );
}

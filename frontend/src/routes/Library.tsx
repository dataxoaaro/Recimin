import { Heart, Plus, Search, X } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { CategoryFilter } from "@/components/CategoryFilter";
import { RecipeCard } from "@/components/RecipeCard";
import { RecipeForm } from "@/components/RecipeForm";
import { EmptyState } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { t } from "@/lib/strings";
import type { RecipeSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Debounce a value so typing does not fire a request per keystroke. */
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function Library() {
  const navigate = useNavigate();
  const [recipes, setRecipes] = React.useState<RecipeSummary[] | null>(null);
  const [error, setError] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [category, setCategory] = React.useState<string | null>(null);
  const [favouritesOnly, setFavouritesOnly] = React.useState(false);
  const [creating, setCreating] = React.useState(false);

  const debouncedQuery = useDebounced(query, 250);

  const load = React.useCallback(() => {
    setError(false);
    api
      .listRecipes({
        q: debouncedQuery || undefined,
        category: category ?? undefined,
        favourite: favouritesOnly || undefined,
      })
      .then(setRecipes)
      .catch(() => setError(true));
  }, [debouncedQuery, category, favouritesOnly]);

  React.useEffect(load, [load]);

  const filtered = debouncedQuery !== "" || category !== null || favouritesOnly;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search
            size={18}
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--color-muted)]"
          />
          <Input
            className="pl-10"
            placeholder={t.searchPlaceholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label={t.searchPlaceholder}
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              aria-label="Clear search"
              className="absolute top-1/2 right-2 inline-flex min-h-11 min-w-11 -translate-y-1/2 items-center justify-center rounded-full text-[var(--color-muted)]"
            >
              <X size={18} aria-hidden />
            </button>
          )}
        </div>
        <button
          onClick={() => setFavouritesOnly((on) => !on)}
          aria-label={t.favourite}
          aria-pressed={favouritesOnly}
          className={cn(
            "inline-flex min-h-12 min-w-12 items-center justify-center rounded-xl border transition-colors",
            favouritesOnly
              ? "border-[var(--color-accent)] text-[var(--color-accent)]"
              : "border-[var(--color-border)] text-[var(--color-muted)]",
          )}
        >
          <Heart size={20} aria-hidden className={favouritesOnly ? "fill-current" : ""} />
        </button>
      </div>

      <CategoryFilter value={category} onChange={setCategory} />

      {error && <p className="text-[var(--color-danger)]">{t.loadFailed}</p>}
      {!error && recipes === null && <p className="text-[var(--color-muted)]">{t.loading}</p>}

      {recipes?.length === 0 &&
        (filtered ? (
          <EmptyState title={t.searchEmptyTitle} body={t.searchEmptyBody} />
        ) : (
          <EmptyState title={t.libraryEmptyTitle} body={t.libraryEmptyBody} />
        ))}

      {recipes && recipes.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {recipes.map((recipe) => (
            <li key={recipe.id}>
              <RecipeCard recipe={recipe} />
            </li>
          ))}
        </ul>
      )}

      <button
        onClick={() => setCreating(true)}
        aria-label={t.add}
        className="fixed right-5 bottom-24 z-10 inline-flex h-16 w-16 items-center justify-center rounded-full bg-[var(--color-accent)] text-white shadow-lg transition-colors hover:bg-[var(--color-accent-strong)]"
      >
        <Plus size={28} aria-hidden />
      </button>

      <RecipeForm
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(recipe) => {
          setCreating(false);
          navigate(`/recipes/${recipe.id}`);
        }}
      />
    </div>
  );
}

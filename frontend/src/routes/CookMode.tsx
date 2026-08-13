import { Check, ChevronLeft, ChevronRight, X } from "lucide-react";
import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useWakeLock } from "@/hooks/useWakeLock";
import { api } from "@/lib/api";
import { deriveSteps, scaleLine } from "@/lib/steps";
import { t } from "@/lib/strings";
import type { Recipe } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Full-screen takeover: no header, no tabs, screen stays awake.
 *
 * Steps are derived from the markdown at render time, never stored.
 */
export function CookMode() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [recipe, setRecipe] = React.useState<Recipe | null>(null);
  const [index, setIndex] = React.useState(0);
  const [showIngredients, setShowIngredients] = React.useState(true);
  const [servings, setServings] = React.useState<number | null>(null);

  useWakeLock(recipe !== null);

  React.useEffect(() => {
    api.getRecipe(Number(id)).then((loaded) => {
      setRecipe(loaded);
      setServings(loaded.servings);
    });
  }, [id]);

  const steps = React.useMemo(
    () => (recipe ? deriveSteps(recipe.instructions_md) : []),
    [recipe],
  );

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") navigate(-1);
      if (event.key === "ArrowRight") setIndex((i) => Math.min(i + 1, steps.length - 1));
      if (event.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navigate, steps.length]);

  if (!recipe) {
    return <p className="p-4 text-[var(--color-muted)]">{t.loading}</p>;
  }

  const atEnd = index >= steps.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[var(--color-bg)]">
      <header className="flex shrink-0 items-center gap-2 border-b border-[var(--color-border)] px-4 py-3 pt-safe">
        <p className="min-w-0 flex-1 truncate font-[family-name:var(--font-display)] text-lg font-semibold">
          {recipe.title}
        </p>
        <button
          onClick={() => navigate(-1)}
          aria-label={t.close}
          className="inline-flex min-h-12 min-w-12 items-center justify-center rounded-full text-[var(--color-muted)]"
        >
          <X size={22} aria-hidden />
        </button>
      </header>

      {recipe.ingredients.length > 0 && (
        <div className="shrink-0 border-b border-[var(--color-border)]">
          <button
            onClick={() => setShowIngredients((open) => !open)}
            className="flex min-h-12 w-full items-center justify-between px-4 text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase"
          >
            Ingredients
            <span className="flex items-center gap-2">
              {recipe.servings != null && servings != null && (
                <span className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <span
                    role="button"
                    tabIndex={0}
                    aria-label="Fewer servings"
                    onClick={() => setServings(Math.max(1, servings - 1))}
                    className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-[var(--color-border)]"
                  >
                    −
                  </span>
                  <span className="w-8 text-center text-base text-[var(--color-fg)]">
                    {servings}
                  </span>
                  <span
                    role="button"
                    tabIndex={0}
                    aria-label="More servings"
                    onClick={() => setServings(servings + 1)}
                    className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-[var(--color-border)]"
                  >
                    +
                  </span>
                </span>
              )}
            </span>
          </button>
          {showIngredients && (
            <ul className="max-h-40 overflow-y-auto px-4 pb-3">
              {recipe.ingredients.map((line) => (
                <li key={line.position} className="py-0.5 text-base leading-relaxed">
                  {scaleLine(line.raw_text, line.qty, recipe.servings, servings ?? 0)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <button
        onClick={() => setIndex((i) => Math.min(i + 1, steps.length - 1))}
        className="flex min-h-0 flex-1 items-start overflow-y-auto p-6 text-left"
        aria-label="Next step"
      >
        {steps.length > 0 ? (
          <p className="text-lg leading-relaxed">{steps[index]}</p>
        ) : (
          <p className="text-[var(--color-muted)]">This recipe has no instructions yet.</p>
        )}
      </button>

      <footer className="shrink-0 border-t border-[var(--color-border)] p-4 pb-safe">
        <div className="mb-3 flex justify-center gap-1.5" aria-hidden>
          {steps.map((_, dot) => (
            <span
              key={dot}
              className={cn(
                "h-2 w-2 rounded-full transition-colors",
                dot === index ? "bg-[var(--color-accent)]" : "bg-[var(--color-border)]",
              )}
            />
          ))}
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="icon"
            aria-label="Previous step"
            disabled={index === 0}
            onClick={() => setIndex((i) => Math.max(i - 1, 0))}
          >
            <ChevronLeft size={22} aria-hidden />
          </Button>
          <span className="flex-1 text-center text-sm text-[var(--color-muted)]">
            {steps.length > 0 ? `${index + 1} / ${steps.length}` : ""}
          </span>
          {atEnd ? (
            <Button size="lg" onClick={() => navigate(-1)}>
              <Check size={20} aria-hidden />
              {t.done}
            </Button>
          ) : (
            <Button
              size="icon"
              aria-label="Next step"
              onClick={() => setIndex((i) => Math.min(i + 1, steps.length - 1))}
            >
              <ChevronRight size={22} aria-hidden />
            </Button>
          )}
        </div>
      </footer>
    </div>
  );
}

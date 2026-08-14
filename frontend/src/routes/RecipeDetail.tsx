import { ArrowLeft, ChefHat, Clock, Heart, ImagePlus, Pencil, Users } from "lucide-react";
import * as React from "react";
import Markdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router-dom";

import { RecipeForm } from "@/components/RecipeForm";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { categoryColour, categoryLabel, useCategories } from "@/hooks/useCategories";
import { api } from "@/lib/api";
import { t } from "@/lib/strings";
import type { Recipe } from "@/lib/types";

/**
 * Full-screen, not a sheet: a recipe is a destination, not an inspection.
 *
 * Markdown is rendered with the default (safe) configuration — no raw HTML
 * plugin. Recipe text will later come from an LLM, so it is untrusted input.
 */
export function RecipeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const categories = useCategories();
  const [recipe, setRecipe] = React.useState<Recipe | null>(null);
  const [error, setError] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [confirmingDelete, setConfirmingDelete] = React.useState(false);
  const fileInput = React.useRef<HTMLInputElement>(null);

  const recipeId = Number(id);

  React.useEffect(() => {
    if (!Number.isFinite(recipeId)) return;
    api.getRecipe(recipeId).then(setRecipe).catch(() => setError(true));
  }, [recipeId]);

  async function onUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !recipe) return;

    const body = new FormData();
    body.append("file", file);
    const response = await fetch(`/api/media?recipe_id=${recipe.id}`, {
      method: "POST",
      body,
      credentials: "include",
    });
    if (!response.ok) return;
    const { id: mediaId } = await response.json();
    setRecipe(await api.patchRecipe(recipe.id, { hero_media_id: mediaId }));
  }

  if (error) return <p className="text-[var(--color-danger)]">{t.loadFailed}</p>;
  if (!recipe) return <p className="text-[var(--color-muted)]">{t.loading}</p>;

  const meta = [
    recipe.total_time_minutes != null && {
      icon: Clock,
      text: t.minutes(recipe.total_time_minutes),
    },
    recipe.servings != null && { icon: Users, text: recipe.yield_text ?? t.servings(recipe.servings) },
  ].filter(Boolean) as { icon: typeof Clock; text: string }[];

  return (
    <div className="-mx-4 -mt-4 pb-24">
      {/* Height is capped rather than left to the aspect ratio. `aspect-[4/3]
          w-full` scales with the window forever: at 1440px it measured 1069px,
          taller than the viewport, so the whole first screen was an empty box.
          With no photo it collapses to a strip — an absent image should not
          cost a third of a phone screen. */}
      <div className="relative w-full bg-[var(--color-surface)]">
        {recipe.hero_media_id ? (
          <img
            src={`/api/media/${recipe.hero_media_id}`}
            alt={recipe.title}
            className="h-[min(45vh,380px)] w-full object-cover"
          />
        ) : (
          <button
            onClick={() => fileInput.current?.click()}
            className="flex h-28 w-full items-center justify-center gap-2 text-[var(--color-muted)] transition-colors hover:text-[var(--color-fg)]"
          >
            <ImagePlus size={20} aria-hidden />
            <span className="text-sm">Add a photo</span>
          </button>
        )}
        <Link
          to="/"
          aria-label="Back"
          className="absolute top-3 left-3 inline-flex min-h-11 min-w-11 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur"
        >
          <ArrowLeft size={20} aria-hidden />
        </Link>
      </div>

      <input
        ref={fileInput}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => void onUpload(e)}
      />

      <div className="mx-auto max-w-[var(--measure)] space-y-6 p-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold">
            {recipe.title}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[var(--color-muted)]">
            <span className="inline-flex items-center gap-1.5">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: categoryColour(categories, recipe.category) }}
              />
              {categoryLabel(categories, recipe.category)}
            </span>
            {meta.map(({ icon: Icon, text }) => (
              <span key={text} className="inline-flex items-center gap-1.5">
                <Icon size={15} aria-hidden />
                {text}
              </span>
            ))}
          </div>
        </div>

        {recipe.source_url && (
          <p className="text-xs text-[var(--color-muted)]">
            From{" "}
            <a
              href={recipe.source_url}
              target="_blank"
              rel="noreferrer noopener"
              className="underline"
            >
              {recipe.source_author ?? recipe.source_site ?? recipe.source_url}
            </a>
          </p>
        )}

        {recipe.ingredients.length > 0 && (
          <section>
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase">
              Ingredients
            </h2>
            {/* leading-snug over leading-relaxed: at ~64px a row only five of
                ten ingredients fitted a phone screen, which is what made the
                page feel oversized. A list is scanned, not read as prose. */}
            <ul className="space-y-1">
              {recipe.ingredients.map((line) => (
                <li key={line.position} className="text-base leading-snug">
                  {line.raw_text}
                  {line.original_text && line.original_text !== line.raw_text && (
                    <span className="block text-xs text-[var(--color-muted)]">
                      {line.original_text}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {recipe.instructions_md && (
          <section>
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase">
              Instructions
            </h2>
            <div className="space-y-3 text-base leading-relaxed [&_li]:ml-5 [&_li]:list-decimal [&_ol]:space-y-2 [&_ul_li]:list-disc">
              <Markdown>{recipe.instructions_md}</Markdown>
            </div>
          </section>
        )}

        {recipe.notes && (
          <section>
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase">
              Notes
            </h2>
            <p className="text-base leading-relaxed whitespace-pre-wrap">{recipe.notes}</p>
          </section>
        )}

        {recipe.tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {recipe.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-[var(--color-border)] px-3 py-1 text-sm text-[var(--color-muted)]"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        <Button
          variant="destructive"
          className="w-full"
          onClick={() => setConfirmingDelete(true)}
        >
          {t.del}
        </Button>
      </div>

      {/* bottom is the shared nav height, not a hardcoded 16 (64px) that
          disagreed with the nav's actual 57px and let content scroll through
          the 7px gap between them. */}
      <div className="fixed inset-x-0 bottom-[var(--nav-height)] z-10 border-t border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-[var(--measure)] items-center gap-3 p-3">
          <Button
            variant="secondary"
            size="icon"
            aria-label={t.favourite}
            onClick={() => void api.toggleFavourite(recipe.id).then(setRecipe)}
          >
            <Heart
              size={20}
              aria-hidden
              className={
                recipe.is_favourite ? "fill-[var(--color-accent)] text-[var(--color-accent)]" : ""
              }
            />
          </Button>
          <Button
            variant="secondary"
            size="icon"
            aria-label={t.edit}
            onClick={() => setEditing(true)}
          >
            <Pencil size={20} aria-hidden />
          </Button>
          <Button size="lg" className="flex-1" asChild>
            <Link to={`/recipes/${recipe.id}/cook`}>
              <ChefHat size={20} aria-hidden />
              {t.cook}
            </Link>
          </Button>
        </div>
      </div>

      <RecipeForm
        open={editing}
        recipe={recipe}
        onClose={() => setEditing(false)}
        onSaved={(saved) => {
          setRecipe(saved);
          setEditing(false);
        }}
      />

      <ConfirmDialog
        open={confirmingDelete}
        title={`Delete "${recipe.title}"?`}
        message="This cannot be undone."
        confirmLabel={t.del}
        onCancel={() => setConfirmingDelete(false)}
        onConfirm={() => void api.deleteRecipe(recipe.id).then(() => navigate("/"))}
      />
    </div>
  );
}

import { Trash2 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import { useCategories } from "@/hooks/useCategories";
import { api } from "@/lib/api";
import { t } from "@/lib/strings";
import type { Recipe } from "@/lib/types";

interface Draft {
  title: string;
  category: string;
  language: string;
  servings: string;
  yield_text: string;
  total_time_minutes: string;
  instructions_md: string;
  notes: string;
  tags: string;
  ingredients: string[];
}

function toDraft(recipe?: Recipe): Draft {
  return {
    title: recipe?.title ?? "",
    category: recipe?.category ?? "dinner",
    language: recipe?.language ?? "en",
    servings: recipe?.servings?.toString() ?? "",
    yield_text: recipe?.yield_text ?? "",
    total_time_minutes: recipe?.total_time_minutes?.toString() ?? "",
    instructions_md: recipe?.instructions_md ?? "",
    notes: recipe?.notes ?? "",
    tags: recipe?.tags.join(", ") ?? "",
    ingredients: recipe?.ingredients.map((line) => line.raw_text) ?? [""],
  };
}

const label = "text-sm text-[var(--color-fg)]/70";

/** Create or edit a recipe. The same sheet serves both. */
export function RecipeForm({
  open,
  onClose,
  onSaved,
  recipe,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (recipe: Recipe) => void;
  recipe?: Recipe;
}) {
  const categories = useCategories();
  const [draft, setDraft] = React.useState<Draft>(() => toDraft(recipe));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Re-seed whenever the sheet opens, so a cancelled edit does not persist.
  React.useEffect(() => {
    if (open) {
      setDraft(toDraft(recipe));
      setError(null);
    }
  }, [open, recipe]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  const setIngredient = (index: number, value: string) =>
    setDraft((prev) => ({
      ...prev,
      ingredients: prev.ingredients.map((line, i) => (i === index ? value : line)),
    }));

  const removeIngredient = (index: number) =>
    setDraft((prev) => ({
      ...prev,
      ingredients: prev.ingredients.filter((_, i) => i !== index),
    }));

  async function save() {
    setBusy(true);
    setError(null);
    const payload = {
      title: draft.title.trim(),
      category: draft.category,
      language: draft.language,
      instructions_md: draft.instructions_md,
      notes: draft.notes || null,
      servings: draft.servings ? Number(draft.servings) : null,
      yield_text: draft.yield_text || null,
      total_time_minutes: draft.total_time_minutes
        ? Number(draft.total_time_minutes)
        : null,
      status: "published" as const,
      ingredients: draft.ingredients
        .map((line) => line.trim())
        .filter(Boolean)
        .map((raw_text) => ({ raw_text })),
      tags: draft.tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    };

    try {
      const saved = recipe
        ? await api.patchRecipe(recipe.id, payload)
        : await api.createRecipe(payload);
      onSaved(saved);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t.saveFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={recipe ? t.edit : "New recipe"}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t.cancel}
          </Button>
          <div className="flex-1" />
          <Button size="lg" onClick={() => void save()} disabled={busy || !draft.title.trim()}>
            {busy ? t.saving : t.save}
          </Button>
        </>
      }
    >
      <label className="block">
        <span className={label}>Title *</span>
        <Input
          className="mt-1"
          value={draft.title}
          onChange={(e) => set("title", e.target.value)}
          placeholder="e.g. Perinteinen mansikkakakku"
        />
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className={label}>Category</span>
          <select
            className="mt-1 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3"
            value={draft.category}
            onChange={(e) => set("category", e.target.value)}
          >
            {categories.map((category) => (
              <option key={category.key} value={category.key}>
                {category.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className={label}>Language</span>
          <select
            className="mt-1 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3"
            value={draft.language}
            onChange={(e) => set("language", e.target.value)}
          >
            <option value="en">English</option>
            <option value="fi">Suomi</option>
          </select>
        </label>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className={label}>Servings</span>
          <Input
            className="mt-1"
            inputMode="numeric"
            value={draft.servings}
            onChange={(e) => set("servings", e.target.value.replace(/\D/g, ""))}
          />
        </label>
        <label className="block">
          <span className={label}>Total time (min)</span>
          <Input
            className="mt-1"
            inputMode="numeric"
            value={draft.total_time_minutes}
            onChange={(e) => set("total_time_minutes", e.target.value.replace(/\D/g, ""))}
          />
        </label>
      </div>

      <label className="block">
        <span className={label}>Yield</span>
        <Input
          className="mt-1"
          value={draft.yield_text}
          onChange={(e) => set("yield_text", e.target.value)}
          placeholder="e.g. 15 palaa"
        />
      </label>

      <div>
        <span className={label}>Ingredients</span>
        <ul className="mt-1 space-y-2">
          {draft.ingredients.map((line, index) => (
            <li key={index} className="flex items-center gap-2">
              <Input
                value={line}
                onChange={(e) => setIngredient(index, e.target.value)}
                placeholder="e.g. 2 dl kermaa"
              />
              <button
                onClick={() => removeIngredient(index)}
                aria-label={`${t.del} ingredient ${index + 1}`}
                className="inline-flex min-h-12 min-w-12 shrink-0 items-center justify-center rounded-xl text-[var(--color-muted)] transition-colors hover:text-[var(--color-danger)]"
              >
                <Trash2 size={18} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
        <Button
          variant="secondary"
          size="sm"
          className="mt-2"
          onClick={() => set("ingredients", [...draft.ingredients, ""])}
        >
          {t.add}
        </Button>
      </div>

      <label className="block">
        <span className={label}>Instructions</span>
        <Textarea
          className="mt-1"
          rows={10}
          value={draft.instructions_md}
          onChange={(e) => set("instructions_md", e.target.value)}
          placeholder={"1. Heat the oven\n2. Mix everything"}
        />
      </label>

      <label className="block">
        <span className={label}>Tags</span>
        <Input
          className="mt-1"
          value={draft.tags}
          onChange={(e) => set("tags", e.target.value)}
          placeholder="e.g. weeknight, freezer, party"
        />
      </label>

      <label className="block">
        <span className={label}>Notes</span>
        <Textarea
          className="mt-1"
          rows={3}
          value={draft.notes}
          onChange={(e) => set("notes", e.target.value)}
        />
      </label>

      {error && (
        <p className="text-sm text-[var(--color-danger)]" role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}

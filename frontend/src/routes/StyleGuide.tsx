import { Clock, Heart, Plus } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, EmptyState } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { applyTheme, readPreference, type ThemePreference } from "@/lib/theme";

/**
 * Every token and component on one page.
 *
 * Kept in the build deliberately. It costs nothing, it is where dark mode gets
 * checked, and it is the closest thing to a visual regression surface without
 * adding a screenshot pipeline.
 */

const TOKENS = [
  "--color-bg",
  "--color-surface",
  "--color-fg",
  "--color-muted",
  "--color-border",
  "--color-accent",
  "--color-accent-strong",
  "--color-amber",
  "--color-amber-strong",
  "--color-danger",
];

const CATEGORY_DOTS: [string, string][] = [
  ["Main course", "#a8502f"],
  ["Soup", "#c0752f"],
  ["Salad", "#5c8f3a"],
  ["Side dish", "#7a9a4e"],
  ["Appetizer", "#b8843a"],
  ["Breakfast", "#d0a83f"],
  ["Bread", "#a07845"],
  ["Savoury baking", "#96613a"],
  ["Sweet baking", "#b8586e"],
  ["Cake", "#c4557f"],
  ["Dessert", "#8a5fa8"],
  ["Drink", "#3a8f96"],
  ["Sauce", "#6a6f7a"],
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function StyleGuide() {
  const [theme, setTheme] = React.useState<ThemePreference>(readPreference);

  function choose(next: ThemePreference) {
    setTheme(next);
    applyTheme(next);
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-4 pb-16">
      <div className="flex items-center justify-between">
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">
          Style guide
        </h1>
        <div className="flex gap-1">
          {(["light", "dark", "system"] as ThemePreference[]).map((value) => (
            <Button
              key={value}
              size="sm"
              variant={theme === value ? "primary" : "secondary"}
              onClick={() => choose(value)}
            >
              {value}
            </Button>
          ))}
        </div>
      </div>

      <Section title="Colour">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {TOKENS.map((token) => (
            <div
              key={token}
              className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] p-2"
            >
              <span
                className="h-8 w-8 shrink-0 rounded-full border border-[var(--color-border)]"
                style={{ background: `var(${token})` }}
              />
              <code className="text-xs">{token.replace("--color-", "")}</code>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Typography">
        <div className="space-y-2">
          <p className="font-[family-name:var(--font-display)] text-3xl font-semibold">
            Display 3xl — page heading
          </p>
          <p className="font-[family-name:var(--font-display)] text-2xl font-semibold">
            Display 2xl — recipe title
          </p>
          <p className="text-lg leading-relaxed">Body lg — cook mode step text</p>
          <p className="text-base leading-relaxed">
            Body base — the workhorse. Ingredients and instructions are read at arm&rsquo;s
            length with dirty hands, so this is the default rather than text-sm.
          </p>
          <p className="text-sm text-[var(--color-muted)]">Small — labels and metadata</p>
          <p className="text-xs text-[var(--color-muted)]">Extra small — attribution</p>
        </div>
      </Section>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm">Small</Button>
          <Button>Medium</Button>
          <Button size="lg">Large</Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Delete</Button>
          <Button disabled>Disabled</Button>
        </div>
        <Button size="icon" aria-label="Add" className="bg-[var(--color-accent)] text-white">
          <Plus size={24} aria-hidden />
        </Button>
      </Section>

      <Section title="Inputs">
        <label className="block">
          <span className="text-sm text-[var(--color-fg)]/70">Label</span>
          <Input className="mt-1" placeholder="e.g. 2 dl cream" />
        </label>
        <Textarea rows={3} placeholder="e.g. weeknight, freezer, party" />
      </Section>

      <Section title="Cards and rows">
        <Card className="p-5">
          <p className="font-[family-name:var(--font-display)] text-base font-medium">
            Perinteinen mansikkakakku
          </p>
          <div className="mt-1 flex items-center gap-2 text-sm text-[var(--color-muted)]">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#c4557f" }} />
            Cake
            <Clock size={16} aria-hidden />
            180 min
            <Heart size={16} aria-hidden className="text-[var(--color-accent)]" />
          </div>
        </Card>
        <EmptyState title="No recipes yet" body="Add one with the + button." />
      </Section>

      <Section title="States">
        <div className="flex flex-wrap gap-2">
          <span className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-[var(--color-amber)] px-3 text-sm">
            <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-amber)]" />
            Draft
          </span>
          <span className="inline-flex min-h-11 items-center rounded-full border border-[var(--color-accent)] bg-black/[0.05] px-3 text-sm font-medium dark:bg-white/[0.06]">
            Active filter
          </span>
          <span className="inline-flex min-h-11 items-center rounded-full border border-[var(--color-border)] px-3 text-sm">
            Inactive filter
          </span>
        </div>
        <p className="text-sm text-[var(--color-danger)]">Import failed</p>
      </Section>

      <Section title="Category dots">
        <div className="grid grid-cols-2 gap-y-2 sm:grid-cols-3">
          {CATEGORY_DOTS.map(([label, colour]) => (
            <div key={label} className="flex items-center gap-2 text-sm">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: colour }} />
              {label}
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

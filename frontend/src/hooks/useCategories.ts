import * as React from "react";

import { api } from "@/lib/api";
import type { Category } from "@/lib/types";

/** The fixed category vocabulary, fetched once and cached for the session. */
let cache: Category[] | null = null;

export function useCategories(): Category[] {
  const [categories, setCategories] = React.useState<Category[]>(cache ?? []);

  React.useEffect(() => {
    if (cache) return;
    api.categories().then((fetched) => {
      cache = fetched;
      setCategories(fetched);
    });
  }, []);

  return categories;
}

export function categoryLabel(categories: Category[], key: string): string {
  return categories.find((c) => c.key === key)?.label ?? key;
}

export function categoryColour(categories: Category[], key: string): string {
  return categories.find((c) => c.key === key)?.colour ?? "var(--color-muted)";
}

import * as React from "react";

import { api } from "@/lib/api";
import type { Category } from "@/lib/types";

/** The fixed category vocabulary, fetched once and cached for the session. */
let cache: Category[] | null = null;

/** The in-flight request is cached too, or every cold view fired its own GET. */
let pending: Promise<Category[]> | null = null;

function fetchCategories(): Promise<Category[]> {
  pending ??= api.categories().then(
    (fetched) => {
      cache = fetched;
      return fetched;
    },
    (error: unknown) => {
      // Let the next mount retry rather than caching the failure for the session.
      pending = null;
      throw error;
    },
  );
  return pending;
}

export function useCategories(): Category[] {
  const [categories, setCategories] = React.useState<Category[]>(cache ?? []);

  React.useEffect(() => {
    if (cache) return;
    let cancelled = false;
    fetchCategories()
      .then((fetched) => {
        if (!cancelled) setCategories(fetched);
      })
      .catch(() => {
        // Views fall back to the raw key and a muted dot; nothing to render here.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return categories;
}

export function categoryLabel(categories: Category[], key: string): string {
  return categories.find((c) => c.key === key)?.label ?? key;
}

export function categoryColour(categories: Category[], key: string): string {
  return categories.find((c) => c.key === key)?.colour ?? "var(--color-muted)";
}

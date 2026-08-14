import * as React from "react";

import { ApiError } from "@/lib/api";
import { t } from "@/lib/strings";

interface ApiData<T> {
  data: T | null;
  /** User-facing message: the server's detail for an ApiError, t.loadFailed otherwise. */
  error: string | null;
  loading: boolean;
  /** Refetch, keeping the current data on screen until the new payload lands. */
  reload: () => Promise<void>;
  /** For mutations whose response already carries the fresh entity. */
  setData: React.Dispatch<React.SetStateAction<T | null>>;
}

/**
 * Load state for a single API call.
 *
 * The fetcher is a dependency: pass a module-level api method or wrap it in
 * useCallback, or every render restarts the load.
 */
export function useApiData<T>(fetcher: () => Promise<T>): ApiData<T> {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  // A response from a superseded fetch must not overwrite fresher data.
  const generation = React.useRef(0);

  const reload = React.useCallback(async () => {
    const ticket = ++generation.current;
    try {
      const fetched = await fetcher();
      if (ticket !== generation.current) return;
      // Keep the old identity when the payload has not changed, so effects and
      // memoised children keyed on the data do not churn while polling.
      setData((current) =>
        JSON.stringify(current) === JSON.stringify(fetched) ? current : fetched,
      );
      setError(null);
      setLoading(false);
    } catch (caught) {
      if (ticket !== generation.current) return;
      setError(caught instanceof ApiError ? caught.message : t.loadFailed);
      setLoading(false);
    }
  }, [fetcher]);

  React.useEffect(() => {
    setLoading(true);
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

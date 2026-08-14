import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { extractSharedUrl } from "@/lib/share";
import { t } from "@/lib/strings";

/**
 * Target of the PWA share sheet (manifest share_target, GET /import).
 *
 * Queues the shared link and hands over to /imports; this page is only ever
 * seen when the queue call fails, at which point the shared URL must stay on
 * screen so it is not lost.
 */
export function ImportShare() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = React.useState<string | null>(null);

  const shared = extractSharedUrl(params);

  const queue = React.useCallback(async () => {
    if (!shared) {
      navigate("/imports", { replace: true });
      return;
    }
    setError(null);
    try {
      const result = await api.queueImport(shared);
      if (result.duplicate && result.recipe_id != null) {
        navigate(`/recipes/${result.recipe_id}`, { replace: true });
      } else {
        navigate("/imports", { replace: true });
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t.importFailed);
    }
  }, [shared, navigate]);

  // Fire once on arrival; StrictMode's double-run must not queue twice.
  const fired = React.useRef(false);
  React.useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    void queue();
  }, [queue]);

  if (!error) {
    return <p className="text-[var(--color-muted)]">{t.adding}</p>;
  }

  return (
    <div className="mx-auto max-w-lg space-y-4">
      <p className="text-sm text-[var(--color-danger)]" role="alert">
        {error}
      </p>
      <p className="text-sm break-all text-[var(--color-muted)]">{shared}</p>
      <div className="flex gap-2">
        <Button onClick={() => void queue()}>{t.retry}</Button>
        <Button variant="secondary" asChild>
          <Link to="/imports">{t.imports}</Link>
        </Button>
      </div>
    </div>
  );
}

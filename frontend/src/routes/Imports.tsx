import { AlertTriangle, Check, Link2, Loader, RefreshCw } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, EmptyState } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { t } from "@/lib/strings";
import type { Job } from "@/lib/types";

const POLL_MS = 3000;
const ACTIVE = new Set(["queued", "running"]);

const STATUS_ICON = {
  queued: Loader,
  running: Loader,
  done: Check,
  failed: AlertTriangle,
  needs_attention: AlertTriangle,
} as const;

const STATUS_COLOUR = {
  queued: "text-[var(--color-muted)]",
  running: "text-[var(--color-amber-strong)]",
  done: "text-[var(--color-muted)]",
  failed: "text-[var(--color-danger)]",
  needs_attention: "text-[var(--color-danger)]",
} as const;

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function Imports() {
  const [jobs, setJobs] = React.useState<Job[] | null>(null);
  const [url, setUrl] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(() => api.listJobs().then(setJobs).catch(() => {}), []);

  React.useEffect(() => {
    void load();
  }, [load]);

  // Poll only while something is in flight, then stop.
  React.useEffect(() => {
    if (!jobs?.some((job) => ACTIVE.has(job.status))) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [jobs, load]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await fetch("/api/import", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      }).then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new ApiError(response.status, body.detail ?? t.importFailed);
        }
      });
      setUrl("");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t.importFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => void submit(e)} className="flex gap-2">
        <div className="relative flex-1">
          <Link2
            size={18}
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[var(--color-muted)]"
          />
          <Input
            className="pl-10"
            type="url"
            inputMode="url"
            placeholder="Paste a recipe link"
            aria-label="Paste a recipe link"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
        </div>
        <Button type="submit" disabled={busy || !url.trim()}>
          {busy ? "Adding…" : t.add}
        </Button>
      </form>

      {error && (
        <p className="text-sm text-[var(--color-danger)]" role="alert">
          {error}
        </p>
      )}

      {jobs === null && <p className="text-[var(--color-muted)]">{t.loading}</p>}
      {jobs?.length === 0 && (
        <EmptyState
          title="No imports yet"
          body="Paste a link above, or share one from your phone."
        />
      )}

      <ul className="space-y-2">
        {jobs?.map((job) => {
          const Icon = STATUS_ICON[job.status];
          const spinning = job.status === "running" || job.status === "queued";
          return (
            <Card key={job.id} className="flex items-center gap-3 p-4">
              <Icon
                size={20}
                aria-hidden
                className={`${STATUS_COLOUR[job.status]} ${spinning ? "animate-spin" : ""}`}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{hostOf(job.input_url)}</p>
                <p className="truncate text-xs text-[var(--color-muted)]">
                  {job.last_error ?? job.stage ?? job.status.replace("_", " ")}
                </p>
              </div>
              {job.recipe_id && (
                <Button variant="secondary" size="sm" asChild>
                  <Link to={`/recipes/${job.recipe_id}`}>Open</Link>
                </Button>
              )}
              {(job.status === "failed" || job.status === "needs_attention") && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    void fetch(`/api/imports/${job.id}/retry`, {
                      method: "POST",
                      credentials: "include",
                    }).then(load)
                  }
                >
                  <RefreshCw size={16} aria-hidden />
                  {t.retry}
                </Button>
              )}
            </Card>
          );
        })}
      </ul>
    </div>
  );
}

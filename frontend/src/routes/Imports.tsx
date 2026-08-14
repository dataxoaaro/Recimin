import { AlertTriangle, Camera, Check, Image, Link2, Loader, RefreshCw } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, EmptyState } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApiData } from "@/hooks/useApiData";
import { api } from "@/lib/api";
import { t } from "@/lib/strings";

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
  const { data: jobs, error: loadError, reload } = useApiData(api.listJobs);
  const [url, setUrl] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [duplicateOf, setDuplicateOf] = React.useState<number | null>(null);
  const photoInput = React.useRef<HTMLInputElement>(null);

  // Poll only while something is in flight, then stop. The dependency is a
  // boolean, so identical payloads (and reload's stable identity) leave the
  // interval alone instead of tearing it down every tick.
  const polling = jobs?.some((job) => ACTIVE.has(job.status)) ?? false;
  React.useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => void reload(), POLL_MS);
    return () => clearInterval(timer);
  }, [polling, reload]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDuplicateOf(null);
    try {
      const result = await api.queueImport(url);
      if (result.duplicate && result.recipe_id != null) setDuplicateOf(result.recipe_id);
      setUrl("");
      await reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t.importFailed);
    } finally {
      setBusy(false);
    }
  }

  async function submitPhotos(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    setDuplicateOf(null);
    try {
      await api.queuePhotoImport(files);
      await reload();
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
          {busy ? t.adding : t.add}
        </Button>
      </form>

      <input
        ref={photoInput}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        className="hidden"
        aria-hidden
        tabIndex={-1}
        onChange={(e) => void submitPhotos(e)}
      />
      <Button
        variant="secondary"
        className="w-full"
        disabled={busy}
        onClick={() => photoInput.current?.click()}
      >
        <Camera size={18} aria-hidden />
        {t.importPhotos}
      </Button>

      {error && (
        <p className="text-sm text-[var(--color-danger)]" role="alert">
          {error}
        </p>
      )}

      {duplicateOf != null && (
        <p className="text-sm text-[var(--color-muted)]" role="status">
          {t.alreadySaved}{" "}
          <Link to={`/recipes/${duplicateOf}`} className="text-[var(--color-accent)] underline">
            Open
          </Link>
        </p>
      )}

      {loadError && <p className="text-[var(--color-danger)]">{loadError}</p>}
      {!loadError && jobs === null && <p className="text-[var(--color-muted)]">{t.loading}</p>}
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
                <p className="flex items-center gap-1.5 truncate text-sm font-medium">
                  {job.kind === "image" && (
                    <Image size={14} aria-hidden className="shrink-0 text-[var(--color-muted)]" />
                  )}
                  {job.kind === "image" ? t.photoImport : hostOf(job.input_url)}
                </p>
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
                    void api
                      .retryJob(job.id)
                      .then(() => reload())
                      .catch(() => setError(t.importFailed))
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

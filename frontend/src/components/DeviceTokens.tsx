import { Check, Copy, Smartphone, Trash2 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { useApiData } from "@/hooks/useApiData";
import { api } from "@/lib/api";
import { t } from "@/lib/strings";
import type { ApiToken } from "@/lib/types";
import { cn } from "@/lib/utils";

/** The device-token list: create, copy once, revoke. Rendered inside a Section. */
export function DeviceTokens() {
  const { data: tokens, error: loadError, reload } = useApiData(api.listTokens);
  const [tokenName, setTokenName] = React.useState("");
  const [freshToken, setFreshToken] = React.useState<string | null>(null);
  const [revoking, setRevoking] = React.useState<ApiToken | null>(null);
  const [copied, setCopied] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);

  async function createToken(event: React.FormEvent) {
    event.preventDefault();
    setActionError(null);
    try {
      const created = await api.createToken(tokenName.trim() || "Phone");
      setFreshToken(created.token);
      setTokenName("");
      await reload();
    } catch {
      setActionError(t.saveFailed);
    }
  }

  return (
    <>
      <p className="text-sm text-[var(--color-muted)]">
        Each phone that shares links to Recimin needs its own key. See{" "}
        <code className="text-xs">docs/shortcut-setup.md</code> for the iPhone Shortcut.
      </p>

      {freshToken && (
        <Card className="border-[var(--color-amber)] p-4">
          <p className="mb-2 text-sm font-medium">
            Copy this now. It will not be shown again.
          </p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-xl bg-[var(--color-bg)] px-3 py-2 text-xs">
              {freshToken}
            </code>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                void navigator.clipboard.writeText(freshToken);
                setCopied(true);
              }}
            >
              {copied ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
            </Button>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="mt-2"
            onClick={() => {
              setFreshToken(null);
              setCopied(false);
            }}
          >
            {t.done}
          </Button>
        </Card>
      )}

      {loadError && <p className="text-sm text-[var(--color-danger)]">{loadError}</p>}

      <ul className="space-y-2">
        {tokens?.map((token) => (
          <Card key={token.id} className="flex items-center gap-3 p-3">
            <Smartphone
              size={18}
              aria-hidden
              className={token.revoked_at ? "text-[var(--color-muted)]" : ""}
            />
            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  "truncate text-sm font-medium",
                  token.revoked_at && "text-[var(--color-muted)] line-through",
                )}
              >
                {token.name}
              </p>
              <p className="text-xs text-[var(--color-muted)]">
                {token.revoked_at
                  ? "Revoked"
                  : token.last_used_at
                    ? `Last used ${token.last_used_at.slice(0, 10)}`
                    : "Never used"}
              </p>
            </div>
            {!token.revoked_at && (
              <button
                onClick={() => setRevoking(token)}
                aria-label={`Revoke ${token.name}`}
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-[var(--color-muted)] transition-colors hover:text-[var(--color-danger)]"
              >
                <Trash2 size={18} aria-hidden />
              </button>
            )}
          </Card>
        ))}
      </ul>

      <form onSubmit={(e) => void createToken(e)} className="flex gap-2">
        <Input
          value={tokenName}
          onChange={(e) => setTokenName(e.target.value)}
          placeholder="e.g. Aaro iPhone"
          aria-label="Device name"
        />
        <Button type="submit">{t.add}</Button>
      </form>

      {actionError && (
        <p className="text-sm text-[var(--color-danger)]" role="alert">
          {actionError}
        </p>
      )}

      <ConfirmDialog
        open={revoking !== null}
        title={`Revoke "${revoking?.name}"?`}
        message="That phone will stop being able to share links."
        confirmLabel="Revoke"
        onCancel={() => setRevoking(null)}
        onConfirm={() => {
          if (revoking) {
            void api
              .revokeToken(revoking.id)
              .then(() => reload())
              .catch(() => setActionError(t.saveFailed));
          }
          setRevoking(null);
        }}
      />
    </>
  );
}

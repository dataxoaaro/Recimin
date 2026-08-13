import { Bell, Check, Copy, Smartphone, Trash2 } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { enablePush, pushPermission } from "@/lib/push";
import { t } from "@/lib/strings";
import { applyTheme, readPreference, type ThemePreference } from "@/lib/theme";
import type { ApiToken } from "@/lib/types";
import { cn } from "@/lib/utils";

const THEMES: { value: ThemePreference; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function Settings() {
  const [theme, setTheme] = React.useState<ThemePreference>(readPreference);
  const [tokens, setTokens] = React.useState<ApiToken[]>([]);
  const [tokenName, setTokenName] = React.useState("");
  const [freshToken, setFreshToken] = React.useState<string | null>(null);
  const [revoking, setRevoking] = React.useState<ApiToken | null>(null);
  const [permission, setPermission] = React.useState(pushPermission);
  const [copied, setCopied] = React.useState(false);

  const load = React.useCallback(() => api.listTokens().then(setTokens).catch(() => {}), []);
  React.useEffect(() => {
    void load();
  }, [load]);

  function choose(next: ThemePreference) {
    setTheme(next);
    applyTheme(next);
  }

  async function createToken(event: React.FormEvent) {
    event.preventDefault();
    const created = await api.createToken(tokenName.trim() || "Phone");
    setFreshToken(created.token);
    setTokenName("");
    await load();
  }

  return (
    <div className="mx-auto max-w-lg space-y-8 pb-8">
      <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">
        {t.settings}
      </h1>

      <Section title="Appearance">
        <div className="flex gap-2">
          {THEMES.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => choose(value)}
              className={cn(
                "min-h-11 flex-1 rounded-full border px-3 text-sm transition-colors",
                theme === value
                  ? "border-[var(--color-accent)] bg-black/[0.05] font-medium dark:bg-white/[0.06]"
                  : "border-[var(--color-border)] hover:bg-black/[0.03] dark:hover:bg-white/[0.04]",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </Section>

      <Section title="Notifications">
        <Card className="p-4">
          {permission === "unsupported" && (
            <p className="text-sm text-[var(--color-muted)]">
              Not available in this browser. On iPhone, add Recimin to your Home Screen first.
            </p>
          )}
          {permission === "granted" && (
            <p className="flex items-center gap-2 text-sm text-[var(--color-muted)]">
              <Check size={16} aria-hidden className="text-[var(--color-accent)]" />
              You will be told when an import finishes.
            </p>
          )}
          {permission === "denied" && (
            <p className="text-sm text-[var(--color-muted)]">
              Blocked. Allow notifications for Recimin in your device settings.
            </p>
          )}
          {permission === "default" && (
            <>
              <p className="mb-3 text-sm text-[var(--color-muted)]">
                Get told when a shared link finishes importing.
              </p>
              <Button
                onClick={() => void enablePush().then(() => setPermission(pushPermission()))}
              >
                <Bell size={18} aria-hidden />
                Turn on notifications
              </Button>
            </>
          )}
        </Card>
      </Section>

      <Section title="Devices">
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

        <ul className="space-y-2">
          {tokens.map((token) => (
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
      </Section>

      <SignOut />

      <ConfirmDialog
        open={revoking !== null}
        title={`Revoke "${revoking?.name}"?`}
        message="That phone will stop being able to share links."
        confirmLabel="Revoke"
        onCancel={() => setRevoking(null)}
        onConfirm={() => {
          if (revoking) void api.revokeToken(revoking.id).then(load);
          setRevoking(null);
        }}
      />
    </div>
  );
}

function SignOut() {
  const { user, signOut } = useAuth();
  return (
    <Section title="Account">
      <Card className="p-4">
        <p className="font-medium">{user?.display_name}</p>
        <p className="text-sm text-[var(--color-muted)]">{user?.email}</p>
      </Card>
      <Button variant="destructive" size="lg" className="w-full" onClick={() => void signOut()}>
        {t.signOut}
      </Button>
    </Section>
  );
}

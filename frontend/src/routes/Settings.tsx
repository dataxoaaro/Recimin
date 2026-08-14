import { Bell, Check } from "lucide-react";
import * as React from "react";

import { DeviceTokens } from "@/components/DeviceTokens";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { enablePush, pushPermission } from "@/lib/push";
import { t } from "@/lib/strings";
import { applyTheme, readPreference, type ThemePreference } from "@/lib/theme";
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
  const [permission, setPermission] = React.useState(pushPermission);

  function choose(next: ThemePreference) {
    setTheme(next);
    applyTheme(next);
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
        <DeviceTokens />
      </Section>

      <Account />
    </div>
  );
}

function Account() {
  const { user, signOut } = useAuth();
  return (
    <Section title="Account">
      <Card className="p-4">
        <p className="font-medium">{user?.display_name}</p>
        <p className="text-sm text-[var(--color-muted)]">{user?.email}</p>
      </Card>
      <ChangePassword />
      <Button variant="destructive" size="lg" className="w-full" onClick={() => void signOut()}>
        {t.signOut}
      </Button>
    </Section>
  );
}

function ChangePassword() {
  const [current, setCurrent] = React.useState("");
  const [replacement, setReplacement] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [changed, setChanged] = React.useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setChanged(false);
    try {
      await api.changePassword(current, replacement);
      setChanged(true);
      setCurrent("");
      setReplacement("");
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 401
          ? t.wrongCurrentPassword
          : t.saveFailed,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-4">
      <form onSubmit={(e) => void onSubmit(e)} className="space-y-3">
        <p className="text-sm font-medium">{t.changePassword}</p>
        <label className="block">
          <span className="text-sm text-[var(--color-fg)]/70">{t.currentPassword}</span>
          <Input
            className="mt-1"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="text-sm text-[var(--color-fg)]/70">{t.newPasswordRule}</span>
          <Input
            className="mt-1"
            type="password"
            autoComplete="new-password"
            minLength={10}
            required
            value={replacement}
            onChange={(e) => setReplacement(e.target.value)}
          />
        </label>
        {error && (
          <p className="text-sm text-[var(--color-danger)]" role="alert">
            {error}
          </p>
        )}
        {changed && (
          <p className="text-sm text-[var(--color-muted)]" role="status">
            {t.passwordChanged}
          </p>
        )}
        <Button type="submit" variant="secondary" disabled={busy}>
          {busy ? t.saving : t.changePassword}
        </Button>
      </form>
    </Card>
  );
}

import * as React from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { t } from "@/lib/strings";

export function Register() {
  const { signUp } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = React.useState({
    email: "",
    password: "",
    display_name: "",
    site_password: "",
  });
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signUp(form);
      navigate("/", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t.saveFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-sm flex-col justify-center p-6">
      <h1 className="mb-8 font-[family-name:var(--font-display)] text-3xl font-semibold">
        {t.register}
      </h1>

      <form onSubmit={onSubmit} className="space-y-3">
        <label className="block">
          <span className="text-sm text-[var(--color-fg)]/70">{t.displayName}</span>
          <Input className="mt-1" required value={form.display_name} onChange={set("display_name")} />
        </label>
        <label className="block">
          <span className="text-sm text-[var(--color-fg)]/70">{t.email}</span>
          <Input className="mt-1" type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
        </label>
        <label className="block">
          <span className="text-sm text-[var(--color-fg)]/70">{t.passwordRule}</span>
          <Input
            className="mt-1"
            type="password"
            autoComplete="new-password"
            minLength={10}
            required
            value={form.password}
            onChange={set("password")}
          />
        </label>
        <label className="block">
          <span className="text-sm text-[var(--color-fg)]/70">{t.sitePassword}</span>
          <Input className="mt-1" type="password" required value={form.site_password} onChange={set("site_password")} />
          <span className="mt-1 block text-xs text-[var(--color-muted)]">{t.sitePasswordHint}</span>
        </label>

        {error && (
          <p className="text-sm text-[var(--color-danger)]" role="alert">
            {error}
          </p>
        )}

        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? t.registering : t.register}
        </Button>
      </form>

      <p className="mt-6 text-sm text-[var(--color-muted)]">
        {t.haveAccount}{" "}
        <Link to="/sign-in" className="text-[var(--color-accent)] underline">
          {t.signIn}
        </Link>
      </p>
    </div>
  );
}

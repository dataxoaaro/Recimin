import * as React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { t } from "@/lib/strings";

export function SignIn() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  // AuthGuard records where the visitor was headed; go back there, not home.
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
      navigate(from, { replace: true });
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 429 ? t.tooManyAttempts : t.signInFailed,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-sm flex-col justify-center p-6">
      <h1 className="mb-1 font-[family-name:var(--font-display)] text-3xl font-semibold">
        {t.appName}
      </h1>
      <p className="mb-8 text-[var(--color-muted)]">{t.tagline}</p>

      <form onSubmit={onSubmit} className="space-y-3">
        <label className="block">
          <span className="text-sm text-[var(--color-fg)]/70">{t.email}</span>
          <Input
            className="mt-1"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="text-sm text-[var(--color-fg)]/70">{t.password}</span>
          <Input
            className="mt-1"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && (
          <p className="text-sm text-[var(--color-danger)]" role="alert">
            {error}
          </p>
        )}

        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? t.signingIn : t.signIn}
        </Button>
      </form>

      <p className="mt-6 text-sm text-[var(--color-muted)]">
        {t.noAccount}{" "}
        <Link to="/register" className="text-[var(--color-accent)] underline">
          {t.register}
        </Link>
      </p>
    </div>
  );
}

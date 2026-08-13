import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { t } from "@/lib/strings";
import { applyTheme, readPreference, type ThemePreference } from "@/lib/theme";
import { cn } from "@/lib/utils";

const THEMES: { value: ThemePreference; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

export function Settings() {
  const { user, signOut } = useAuth();
  const [theme, setTheme] = React.useState<ThemePreference>(readPreference);

  function choose(next: ThemePreference) {
    setTheme(next);
    applyTheme(next);
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold">
        {t.settings}
      </h1>

      <Card className="p-5">
        <p className="font-medium">{user?.display_name}</p>
        <p className="text-sm text-[var(--color-muted)]">{user?.email}</p>
      </Card>

      <div>
        <p className="mb-2 text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase">
          Appearance
        </p>
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
      </div>

      <Button variant="destructive" size="lg" className="w-full" onClick={() => void signOut()}>
        {t.signOut}
      </Button>
    </div>
  );
}

import { BookOpen, Download, Settings } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { t } from "@/lib/strings";
import { cn } from "@/lib/utils";

const TABS = [
  { to: "/", label: t.library, icon: BookOpen, end: true },
  { to: "/imports", label: t.imports, icon: Download, end: false },
];

/**
 * Header plus bottom tab bar. A deliberate divergence from Arboretium, whose
 * primary loop is map interaction; Recimin's is thumb-driven browsing.
 */
export function AppShell() {
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4">
        <span className="font-[family-name:var(--font-display)] text-xl font-semibold text-[var(--color-accent)]">
          {t.appName}
        </span>
        <NavLink
          to="/settings"
          aria-label={t.settings}
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-[var(--color-muted)] transition-colors hover:bg-black/5 dark:hover:bg-white/[0.06]"
        >
          <Settings size={20} aria-hidden />
        </NavLink>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto p-4">
        <Outlet />
      </main>

      <nav className="shrink-0 border-t border-[var(--color-border)] bg-[var(--color-surface)] pb-safe">
        <div className="flex">
          {TABS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5",
                  "transition-colors",
                  isActive
                    ? "text-[var(--color-accent)]"
                    : "text-[var(--color-muted)] hover:text-[var(--color-fg)]",
                )
              }
            >
              <Icon size={22} aria-hidden />
              <span className="text-xs font-medium">{label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}

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
      <header className="shrink-0 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <span className="font-[family-name:var(--font-display)] text-xl font-semibold text-[var(--color-accent)]">
            {t.appName}
          </span>
          <NavLink
            to="/settings"
            aria-label={t.settings}
            className="-mr-2 inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-[var(--color-muted)] transition-colors hover:bg-black/5 dark:hover:bg-white/[0.06]"
          >
            <Settings size={20} aria-hidden />
          </NavLink>
        </div>
      </header>

      {/* The container is here rather than per route so nothing can full-bleed
          by omission. Without it every child stretched to the window: at 1440px
          the ingredient list ran to 170 characters a line. */}
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl p-4">
          <Outlet />
        </div>
      </main>

      <nav className="h-[var(--nav-height)] shrink-0 border-t border-[var(--color-border)] bg-[var(--color-surface)] pb-safe">
        <div className="mx-auto flex h-full max-w-5xl">
          {TABS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex h-full flex-1 flex-col items-center justify-center gap-0.5",
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

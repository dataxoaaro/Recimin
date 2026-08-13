/**
 * Theme handling.
 *
 * The stored value is a *preference* ("system" included). The applied value is
 * always concrete: `data-theme` is set to "light" or "dark" on the root element
 * and never removed.
 *
 * That indirection matters because two things read the theme — the CSS custom
 * properties and Tailwind's `dark:` variant — and they must agree. Binding the
 * variant to `prefers-color-scheme` while the tokens follow an attribute makes
 * them disagree whenever the manual toggle opposes the OS.
 */

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const KEY = "recimin-theme";

function systemTheme(): ResolvedTheme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function readPreference(): ThemePreference {
  const stored = localStorage.getItem(KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

export function resolve(preference: ThemePreference): ResolvedTheme {
  return preference === "system" ? systemTheme() : preference;
}

export function applyTheme(preference: ThemePreference): void {
  if (preference === "system") localStorage.removeItem(KEY);
  else localStorage.setItem(KEY, preference);
  document.documentElement.setAttribute("data-theme", resolve(preference));
}

/**
 * Call once before first paint, so the theme does not flash, and keep following
 * the OS while the preference is "system".
 */
export function initTheme(): void {
  applyTheme(readPreference());
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      if (readPreference() === "system") applyTheme("system");
    });
}

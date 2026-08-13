import { beforeEach, describe, expect, it, vi } from "vitest";

import { applyTheme, readPreference, resolve } from "@/lib/theme";

function setSystemDark(dark: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: dark,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

describe("theme", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    setSystemDark(false);
  });

  it("defaults to system", () => {
    expect(readPreference()).toBe("system");
  });

  it("resolves system to the OS preference", () => {
    setSystemDark(true);
    expect(resolve("system")).toBe("dark");
    setSystemDark(false);
    expect(resolve("system")).toBe("light");
  });

  it("always writes a concrete data-theme", () => {
    // The whole point: the CSS tokens and Tailwind's dark: variant both read
    // this attribute, so it can never be absent or they disagree.
    applyTheme("system");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    setSystemDark(true);
    applyTheme("system");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("an explicit choice overrides a contrary OS preference", () => {
    setSystemDark(true);
    applyTheme("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(readPreference()).toBe("light");
  });

  it("returning to system clears the stored preference", () => {
    applyTheme("dark");
    expect(localStorage.getItem("recimin-theme")).toBe("dark");
    applyTheme("system");
    expect(localStorage.getItem("recimin-theme")).toBeNull();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";

describe("Button", () => {
  it("meets the touch-target floor at every size", () => {
    // Arboretium's rule, and the reason the sizes deviate from shadcn defaults:
    // this app is used with greasy hands at arm's length.
    const floors = { sm: "min-h-10", md: "min-h-12", lg: "min-h-14" } as const;
    for (const [size, floor] of Object.entries(floors)) {
      const { container } = render(<Button size={size as keyof typeof floors}>x</Button>);
      expect(container.firstElementChild?.className).toContain(floor);
    }
  });

  it("renders destructive as text-only, never a filled red", () => {
    render(<Button variant="destructive">Delete</Button>);
    const button = screen.getByRole("button", { name: "Delete" });
    expect(button.className).toContain("bg-transparent");
    expect(button.className).not.toContain("bg-[var(--color-danger)] ");
  });

  it("is focusable with a visible ring", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button").className).toContain("focus-visible:ring-2");
  });
});
